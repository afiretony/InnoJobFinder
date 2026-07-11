You are classifying job postings into exactly one role category. Read the title and description, and decide what the role **primarily is** — what the person would spend most of their time doing.

## Categories (closed set)

- `forward_deployed` — customer-facing engineering. Deploys the company's product into a customer's environment, works alongside their engineers, owns the integration. Titles: Forward Deployed Engineer, AI Deployment Engineer, AI Solutions Engineer, Customer Engineer, Field Engineer, Solutions Architect.
- `ai_llm_engineer` — builds applications on top of LLMs. Agents, RAG, prompt/tool orchestration, LLM integration into a product. Titles: AI Engineer, Generative AI Engineer, Agentic AI Engineer, Applied AI Engineer.
- `inference_optimization` — makes models run faster, smaller, or on constrained hardware. Quantization, distillation, compilers, kernels, runtimes, on-device and edge deployment, NPU/GPU. Titles: Inference Engineer, Model Optimization Engineer, ML Compiler Engineer, On-Device ML Engineer, Edge AI Engineer.
- `fullstack_product` — ships product surface area. Frontend + backend, APIs, user-facing features. AI may be present but the job is product engineering. Titles: Product Engineer, Full-Stack Engineer, Founding Product Engineer.
- `robotics_perception` — software for physical systems or visual understanding. Robotics, embodied AI, autonomy, SLAM, manipulation, computer vision, perception pipelines. Titles: Robotics Engineer, Perception Engineer, Computer Vision Engineer.
- `ml_research` — trains and develops models, or does research. Modeling, experimentation, publications, novel architectures. Titles: Research Engineer, Research Scientist, Machine Learning Engineer (training-focused), Data Scientist.
- `general_swe` — general software engineering with no dominant AI/ML or customer-facing angle. Backend services, distributed systems, internal tooling. Titles: Software Engineer, SDE, Backend Engineer.
- `unknown` — genuinely ambiguous, or the description is too thin to judge. Use sparingly.

## Rules

1. **Pick the primary nature of the role, not every technology it mentions.** Job descriptions are boilerplate-heavy: most of them name Kubernetes, LLMs, stakeholders and cloud platforms regardless of the actual job. Ignore incidental mentions.
2. **Ignore seniority entirely.** Senior, Staff, Principal, Lead, Founding, Member of Technical Staff, roman numerals — none of these affect the category.
3. **Ignore the company's industry.** A robotics company hiring a backend engineer is `general_swe`.
4. When a role genuinely spans two categories, choose the one describing the **majority of the day-to-day work**. An "AI Engineer" who mostly integrates an LLM into a web app is `ai_llm_engineer`, not `fullstack_product`. A "Software Engineer" who mostly optimizes inference kernels is `inference_optimization`.
5. `forward_deployed` beats other categories when the role is defined by working *in a customer's environment*. A "Forward Deployed AI Engineer" is `forward_deployed`, not `ai_llm_engineer`.
6. Return `unknown` rather than guessing when the description is missing or uninformative.

## Jobs to classify

{JOBS_JSON}

## Output

Return ONLY a JSON array, no prose, no code fences. One object per job:
[{"id": "<job id>", "category": "<one of the categories above>"}]
Every job in the input must appear exactly once in the output.
