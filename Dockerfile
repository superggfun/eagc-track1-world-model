FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt requirements-report.txt requirements-optional-sim.txt pyproject.toml ./
COPY main.py config.yaml README.md SUBMISSION_VERSION.txt ./
COPY src ./src
COPY assets ./assets
COPY docs ./docs
COPY tests ./tests
COPY tools ./tools
COPY submission_package ./submission_package
COPY docker ./docker

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

# Track 1 harness smoke test (adjust as needed)
# docker run --rm -v %cd%/outputs:/app/outputs eagc-track1-agent:v0.17.6 \
#   python -m harness.run_track1 --env local_sim --episode-id local-explore-book-relocated --output-dir /app/outputs/local_sim_track1_demo --validate
#
# Official runtime placeholder (fails closed until official API details are wired):
# docker run --rm -e EAGC_EPISODE_ID=hidden_episode -e EAGC_OUTPUT_DIR=/app/outputs/official \
#   -v %cd%/outputs:/app/outputs eagc-track1-agent:v0.17.6 \
#   python -m harness.run_official --output-dir /app/outputs/official --validate

CMD ["python", "tools/run_test_suite.py", "--tier", "fast"]
