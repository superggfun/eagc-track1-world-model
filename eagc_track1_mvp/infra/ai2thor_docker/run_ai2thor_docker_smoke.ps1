param(
    [string]$ImageName = "ai2thor-render-smoke:latest",
    [string]$Platform = "cloud",
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

docker build -f (Join-Path $RepoRoot "infra\ai2thor_docker\Dockerfile.ai2thor-smoke") -t $ImageName $RepoRoot

docker run --rm --gpus all `
    -e NVIDIA_DRIVER_CAPABILITIES=all `
    -v "$RepoRoot\outputs:/app/outputs" `
    $ImageName `
    python3 tools/check_ai2thor_rendering_env.py

if ($Platform -eq "default") {
    docker run --rm --gpus all `
        -e NVIDIA_DRIVER_CAPABILITIES=all `
        -v "$RepoRoot\outputs:/app/outputs" `
        $ImageName `
        xvfb-run -s "-screen 0 1024x768x24" python3 tools/run_ai2thor_minimal_render_test.py --platform default --timeout-seconds $TimeoutSeconds
} else {
    docker run --rm --gpus all `
        -e NVIDIA_DRIVER_CAPABILITIES=all `
        -v "$RepoRoot\outputs:/app/outputs" `
        $ImageName `
        python3 tools/run_ai2thor_minimal_render_test.py --platform cloud --timeout-seconds $TimeoutSeconds
}
