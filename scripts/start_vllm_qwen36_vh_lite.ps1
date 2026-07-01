param(
    [string]$ContainerName = "eagc-vllm-qwen36-vh-lite",
    [int]$HostPort = 8001,
    [int]$ContainerPort = 8000,
    [string]$ModelName = "qwen3.6-35b-nvfp4",
    [int]$MaxModelLen = 32768,
    [int]$MaxNumSeqs = 1,
    [double]$GpuMemoryUtilization = 0.80,
    [switch]$ForceRun
)

$ErrorActionPreference = "Stop"

function Run-DockerJsonLines {
    param([string[]]$DockerArgs)
    $raw = & docker @DockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($DockerArgs -join ' ') failed"
    }
    return $raw
}

Write-Host "Inspecting existing Docker containers read-only. No existing container will be removed or modified."

$existingLite = & docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}"
if ($existingLite -contains $ContainerName) {
    $running = & docker inspect -f "{{.State.Running}}" $ContainerName
    if ($running -eq "true") {
        Write-Host "$ContainerName is already running on host port $HostPort."
        exit 0
    }
    Write-Host "Starting existing stopped container $ContainerName."
    & docker start $ContainerName
    exit $LASTEXITCODE
}

$containers = @()
$dockerLines = Run-DockerJsonLines @("ps", "--format", "{{json .}}")
foreach ($line in $dockerLines) {
    if (-not [string]::IsNullOrWhiteSpace($line)) {
        $obj = $line | ConvertFrom-Json
        $isCandidate = ($obj.Ports -match ":8000->") -or ($obj.Image -match "vllm") -or ($obj.Names -match "vllm|qwen")
        if ($isCandidate) {
            $containers += $obj
        }
    }
}

if ($containers.Count -eq 0) {
    Write-Error "Could not infer the original vLLM container. Start aborted. Please provide a manual docker run command or ensure the original vLLM container is visible in docker ps."
    exit 2
}

if ($containers.Count -gt 1) {
    Write-Host "Multiple possible vLLM containers found:"
    $containers | ForEach-Object { Write-Host "- $($_.Names) image=$($_.Image) ports=$($_.Ports)" }
    Write-Error "Start aborted to avoid using the wrong image or mounts."
    exit 2
}

$source = $containers[0]
$sourceName = $source.Names
$sourceImage = $source.Image

Write-Host "Candidate original vLLM container: $sourceName"
Write-Host "Image: $sourceImage"
Write-Host "This script will create a separate container named $ContainerName using --volumes-from $sourceName."
Write-Host "Original container will not be stopped, deleted, or modified."

if (-not $ForceRun) {
    Write-Host "Dry run only. Re-run with -ForceRun to create the lightweight container."
    Write-Host "Planned settings: max_model_len=$MaxModelLen gpu_memory_utilization=$GpuMemoryUtilization max_num_seqs=$MaxNumSeqs host_port=$HostPort"
    exit 0
}

$command = @(
    "run", "-d",
    "--name", $ContainerName,
    "--gpus", "all",
    "-p", "${HostPort}:${ContainerPort}",
    "--volumes-from", $sourceName,
    $sourceImage,
    "python", "-m", "vllm.entrypoints.openai.api_server",
    "--host", "0.0.0.0",
    "--port", "$ContainerPort",
    "--model", $ModelName,
    "--served-model-name", $ModelName,
    "--max-model-len", "$MaxModelLen",
    "--max-num-seqs", "$MaxNumSeqs",
    "--gpu-memory-utilization", "$GpuMemoryUtilization"
)

Write-Host "Creating lightweight vLLM container $ContainerName on port $HostPort."
& docker @command
exit $LASTEXITCODE
