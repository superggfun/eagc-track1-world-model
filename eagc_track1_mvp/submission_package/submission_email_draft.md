# Submission Email Draft

To: [OFFICIAL_SUBMISSION_EMAIL]

Subject: EAGC 2026 Track 1 Qualification Submission - [TEAM_OR_PROJECT_NAME]

Dear EAGC 2026 Organizing Committee,

We are submitting the qualification materials for our EAGC 2026 Track 1 project, [TEAM_OR_PROJECT_NAME].

The package includes:

- source package / GitHub-ready project files,
- Dockerfile and Docker run instructions,
- technical report draft with HTML/PDF fallback status,
- reproducibility statement,
- training-resource disclosure,
- system limitations statement,
- open-source statement,
- demo commands and local test-suite instructions,
- checksums for key submission bundle files.

The current system is a local Track 1 MVP and readiness baseline. It includes LocalSim, an official-style Track 1 procedure runner, visual-local hybrid evidence reporting, ALFRED synthetic fixture conversion, and VirtualHome manual-play simulator evidence smoke. The VirtualHome evidence path validates scene graph extraction, fixed household program execution, frame export, single-frame Qwen vision comparison, multi-frame visual grounding, and a local VirtualHome + vLLM resource profile.

No model training or fine-tuning has been performed. The system uses a local open-source Qwen3.6-35B-A3B-NVFP4 model through a local vLLM endpoint for inference. No online model APIs are used during local evaluation runs.

Large external assets and model weights are not redistributed in the source package. In particular, the submission package does not include Qwen model weights, VirtualHome executable/assets, ALFRED data, ProcTHOR/Habitat/AI2-THOR assets, raw output frames, or raw Qwen responses unless the final official instructions specifically request such runtime artifacts.

Please confirm receipt of this submission package and let us know if the final qualification process requires a Docker image tar, a registry URL, mounted model weights, an external inference endpoint, or any additional official runtime schema.

Best regards,

[TEAM_NAME]

[CONTACT_NAME]

[CONTACT_EMAIL]
