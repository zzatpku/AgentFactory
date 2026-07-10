# AgentFactory: A Self-Evolving Framework Through Executable Subagent Accumulation and Reuse

<p align="center">
  <strong>Accepted at <a href="https://2026.aclweb.org/program/demo/">ACL 2026 System Demonstrations</a></strong>
</p>

AgentFactory is a self-evolving agent framework that preserves successful task solutions as **executable subagent code** rather than textual experience. These subagents are continuously refined based on execution feedback, becoming increasingly robust and efficient as more tasks are encountered. Since all saved subagents are pure Python code with standardized documentation, they are portable across any Python-capable system.

<p align="center">
  <a href="https://2026.aclweb.org/program/demo/"><img src="https://img.shields.io/badge/Accepted-ACL%202026%20System%20Demonstrations-brightgreen" alt="Accepted at ACL 2026 System Demonstrations"></a>
  <a href="https://aclanthology.org/2026.acl-demo.81/"><img src="https://img.shields.io/badge/Paper-ACL%20Anthology-blue" alt="Paper on ACL Anthology"></a>
  <a href="https://arxiv.org/abs/2603.18000"><img src="https://img.shields.io/badge/Preprint-arXiv-red" alt="Preprint on arXiv"></a>
  <a href="https://youtu.be/iKSsuAXJHW0"><img src="https://img.shields.io/badge/Demo-YouTube-blue" alt="Demo Video"></a>
</p>

> Official implementation of [AgentFactory: A Self-Evolving Framework Through Executable Subagent Accumulation and Reuse](https://aclanthology.org/2026.acl-demo.81/), published in the **ACL 2026 System Demonstrations** proceedings.

<p align="center">
  <img src="figures/pipeline.png" alt="AgentFactory Pipeline" width="100%">
</p>

## How It Works

AgentFactory follows a three-phase lifecycle:

- **Install** — Decompose new tasks into sub-problems and construct specialized subagents from scratch. Successfully executed subagents are saved as reusable Python scripts with accompanying `SKILL.md` documentation.
- **Self-Evolve** — When encountering similar tasks, retrieve saved subagents, detect their limitations, and autonomously modify them to be more robust and general-purpose based on execution feedback.
- **Deploy** — Export mature subagents as standalone Python modules for use in other AI frameworks (e.g., LangChain, AutoGen, Claude Code) by providing the external agent with the subagent code and `SKILL.md` descriptions.

### Architecture

AgentFactory has three main components:

**Meta-Agent** — The central orchestrator. It decomposes complex problems, dynamically allocates relevant tools to each subagent (rather than exposing the full toolset), and iteratively refines subagents based on execution results.

**Skill System** — Three levels of skills:
- *Meta Skills*: Built-in orchestration primitives — `create_subagent`, `run_subagent`, `modify_subagent`, `list_saved_subagents`, `view_subagent_code`, `get_skill_description`, `finish`.
- *Tool Skills*: Built-in tools — `web_search` (Serper), `web_reading` (Jina), `browser_automation` (Playwright), `shell_command`.
- *Subagent Skills*: Dynamically created and refined Python modules that encapsulate successful task-solving patterns. These grow and improve over time.

**Workspace Manager** — Provides isolated execution environments per task, ensuring subagent creation and modification does not corrupt the shared skill library.

## Evaluation

We compare AgentFactory against ReAct and a Self-Evolving Agent with textual experience baseline on 30 real-world tasks (Batch 1: initial construction; Batch 2: transfer evaluation with saved subagents). Metric: average output tokens per task for the orchestrating model (lower = more efficient reuse).

| Method | Task Setting | Opus 4.6 | Sonnet 4.6 |
|---|---|---|---|
| ReAct | Batch 1 | 8298 | 6893 |
| ReAct | Batch 2 | 7022 | 7029 |
| Self-Evolving Agents | Batch 1 (from scratch) | 8608 | 8163 |
| Self-Evolving Agents | Batch 2 (w/ saved) | 6210 | 8223 |
| **AgentFactory** | **Batch 1 (from scratch)** | **4324** | **9199** |
| **AgentFactory** | **Batch 2 (w/ saved)** | **2971** | **3862** |

Reusing executable subagents on Batch 2 reduces orchestration cost by up to **57%** compared to ReAct. Notably, with Opus 4.6, AgentFactory already shows significant savings within Batch 1 itself, as the model recognizes opportunities to reuse subagents created from earlier tasks in the same batch.

## Setup

### 1. Install Dependencies

```bash
conda create -n agentfactory python=3.12
conda activate agentfactory
pip install openai requests playwright flask flask_cors
```

### 2. Configure API Keys

Edit `.env` file and fill in your API keys:

```bash
# Model Selection (OPENAI_STYLE or ANTHROPIC_STYLE)
MODEL_PROTOCOL=OPENAI_STYLE

# Claude API
LLM_URL_CLAUDE=https://your-api-endpoint/v1
LLM_API_KEY_CLAUDE=your-claude-api-key
LLM_MODEL_CLAUDE=claude-opus-4-6

# MiniMax API
LLM_URL_MINIMAX=https://api.minimaxi.com/v1
LLM_API_KEY_MINIMAX=your-minimax-api-key
LLM_MODEL_MINIMAX=MiniMax-M2.7

# Tool APIs
SERPER_API_KEY=your-serper-api-key   # Get from https://serper.dev
JINA_API_KEY=your-jina-api-key       # Get from https://jina.ai
```

Switch between models by changing `MODEL_PROTOCOL` in `.env` (options: `OPENAI_STYLE` or `ANTHROPIC_STYLE`).

### 3. Install Chrome

Browser-based tasks (e.g., web automation via Playwright) require Google Chrome. Make sure Chrome is installed on your machine before running these tasks.

### 4. Replace Placeholder Paths

In `data/questions/questions_round1.jsonl` and `data/questions/questions_round2.jsonl`, replace all occurrences of `<Absolute_Path_to_AgentFactory>` with the actual absolute path to this directory. For example:

```txt
<Absolute_Path_to_AgentFactory>/data/audio/qq_music_taylor.mp3
```

should become:

```txt
/home/user/AgentFactory/data/audio/qq_music_taylor.mp3
```

## Running Tests

```bash
python run.py --question-file data/questions/questions_round1.jsonl
```

Optional flags:

- `--human-confirm` — pause for human confirmation when finishing
- `--no-save` — do not save subagent skills after completion

## Deploy to Claude Code

`prompt4cc.txt` is a ready-to-use prompt for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). To deploy the saved subagents to Claude Code, simply paste the content of `prompt4cc.txt` into Claude Code and replace `<Absolute_Path_to_AgentFactory>` with the actual absolute path to this directory. For example, if your project is at `/home/user/AgentFactory`, replace all occurrences accordingly. Claude Code will then be able to read the subagent code and use them to solve tasks.

## Web Demo

Start the web server:

```bash
python3 web_interface/app.py --port 5050
```

Then open `http://localhost:5050` in your browser. To have the agent solve a task described in an audio file, enter:

```txt
Help me complete a task. The detailed description of the task is in the audio file <your_absolute_path_to_audio>
```

For example, using the included sample audio:

```txt
Help me complete a task. The detailed description of the task is in the audio file /home/user/AgentFactory/data/audio/tencent_doc_en.mp3
```

Replace the path with the actual absolute path to the audio file on your machine.

## Visualizing Trajectories

Open `visualize_trajectory.html` in a browser, then select a trajectory JSON file to visualize the agent's execution process.

## Recorded Demonstrations

The `trajectory/` directory contains saved execution trajectories that correspond to the demonstrations referenced in the paper:

- **`trajectory/qq_music/`** — Two runs of the QQ Music task.
  - `first_time.json` — First attempt; the agent creates subagents from scratch.
  - `second_time.json` — Second attempt; the agent reuses subagents created in the first run.

- **`trajectory/tencent_doc/`** — Three runs of the Tencent Docs task.
  - `first_time.json` — First attempt with a text-based instruction; the agent creates subagents from scratch.
  - `second_time.json` — Second attempt with text; the agent reuses previously created subagents.
  - `third_time.json` — Third attempt with an audio-based instruction. After the QQ Music runs had already produced an `audio_transcriber` subagent, the agent directly reuses it here to transcribe the audio and solve the task.

<p align="center">
  <img src="figures/audio-evolve.png" alt="QQ Music & Tencent Docs Demonstration" width="100%">
</p>

- **`trajectory/readme/`** — Three sequential runs demonstrating the self-evolution process, where the agent progressively builds and refines its subagent repertoire across tasks.

<p align="center">
  <img src="figures/readme-evolve.png" alt="Self-Evolution Demonstration" width="85%">
</p>

## Citation

```bibtex
@inproceedings{zhang-etal-2026-agentfactory,
    title = "{A}gent{F}actory: A Self-Evolving Framework Through Executable Subagent Accumulation and Reuse",
    author = "Zhang, Zhang  and
      Lu, Shuqi  and
      Qian, Hongjin  and
      He, Di  and
      Liu, Zheng",
    editor = "Durrett, Greg  and
      Jian, Ping",
    booktitle = "Proceedings of the 64th Annual Meeting of the {A}ssociation for {C}omputational {L}inguistics (Volume 3: System Demonstrations)",
    month = jul,
    year = "2026",
    address = "San Diego, California, United States",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2026.acl-demo.81/",
    doi = "10.18653/v1/2026.acl-demo.81",
    pages = "819--828",
    ISBN = "979-8-89176-392-0",
    abstract = "Building LLM-based agents has become increasingly important. Recent works on LLM-based agent self-evolution primarily record successful experiences as textual prompts or reflections, which cannot reliably guarantee efficient task re-execution in complex scenarios. We propose AgentFactory, a new self-evolution paradigm that preserves successful task solutions as executable subagent code rather than textual experience. Crucially, these subagents are continuously refined based on execution feedback, becoming increasingly robust and efficient as more tasks are encountered. Saved subagents are pure Python code with standardized documentation, enabling portability across any Python-capable system. We demonstrate that AgentFactory enables continuous capability accumulation: its library of executable subagents grows and improves over time, progressively reducing the effort required for similar tasks without manual intervention. Our implementation is open-sourced at \url{https://github.com/zzatpku/AgentFactory}, and our demonstration video is available at \url{https://youtu.be/iKSsuAXJHW0}."
}
```
