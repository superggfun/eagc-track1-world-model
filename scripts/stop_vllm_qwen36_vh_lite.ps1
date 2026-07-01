param(
    [string]$ContainerName = "eagc-vllm-qwen36-vh-lite"
)

$ErrorActionPreference = "Stop"

Write-Host "Stopping lightweight vLLM container only: $ContainerName"
Write-Host "The original vLLM container is not modified."

$exists = & docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}"
if ($exists -notcontains $ContainerName) {
    Write-Host "$ContainerName does not exist. Nothing to stop."
    exit 0
}

$running = & docker inspect -f "{{.State.Running}}" $ContainerName
if ($running -eq "true") {
    & docker stop $ContainerName
    exit $LASTEXITCODE
}

Write-Host "$ContainerName exists but is not running."
exit 0
