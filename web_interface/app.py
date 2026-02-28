"""
Flask web interface for the Meta-Agent pipeline.
Extends the existing pipeline without modifying it.
"""

import json
import os
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import sys

# Add parent directory to path to import existing modules
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from meta_agent import MetaAgent
from meta_tools import call_llm
from prompts import SYSTEM_PROMPT
from skills_utils import list_all_skills

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'meta-agent-secret-key-' + str(uuid.uuid4())
CORS(app)

# Store conversation history in memory (in production, use a database)
conversations = {}

def create_agent():
    """Create a new MetaAgent instance without human confirm."""
    return MetaAgent(
        verbose=True,
        save_on_finish=True,
        human_confirm=False
    )

@app.route('/')
def index():
    """Main page with the chat interface."""
    return render_template('index.html')

@app.route('/api/start', methods=['POST'])
def start_conversation():
    """Start a new conversation with a question."""
    data = request.json
    question = data.get('question', '').strip()

    if not question:
        return jsonify({'error': 'Question is required'}), 400

    # Create a new conversation ID
    conv_id = str(uuid.uuid4())

    # Initialize conversation state
    conversations[conv_id] = {
        'id': conv_id,
        'question': question,
        'created_at': datetime.now().isoformat(),
        'status': 'running',  # running, waiting_confirm, finished
        'steps': [],
        'messages': [],
        'trajectory': [],
        'final_answer': None,
        'agent': None,
        'iteration': 0,
        'waiting_for_input': False,
        'last_response': None,
        'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S")
    }

    conv = conversations[conv_id]

    # Create agent and start processing
    agent = create_agent()
    conv['agent'] = agent

    # Initialize agent state similar to agent.run() but without the loop
    agent.trajectory = []
    agent.messages = []
    agent.current_skills = []
    agent.viewed_skill_descriptions = set()
    agent.viewed_subagent_codes = set()
    agent.modified_skills = {}
    agent.correct_answer = None

    agent.current_workspace = os.path.join(
        PARENT_DIR, "workspace", conv['timestamp'], "q0"
    )
    os.makedirs(agent.current_workspace, exist_ok=True)

    # Get all available skills
    all_skills = list_all_skills()
    skill_info = "\n".join([f"- {s['name']} ({s['type']})" for s in all_skills])

    initial_content = f"""Question: {question}

You are a deep research agent. When you create subagents to help solve this problem, they must be GENERAL - your subagent should NOT contain any content specific to this question only. The subagent you create should be able to help with general deep research tasks, not just this specific one. For example, if you create a subagent to help search for information, it should take any research topic as input and work independently - it should NOT have hardcoded search queries or topic-specific logic.

CRITICAL RULE: Each response must contain AT MOST ONE <action>...</action><params>...</params> block, then STOP IMMEDIATELY.
- NEVER write <response> tags — they are RESERVED for the system. If you write <response> yourself, it is hallucination and will be rejected.
- NEVER predict, simulate, or fabricate what the system will return — wait for the actual result in the next message.
- NEVER chain multiple actions in one response — only the first one will be executed, the rest are wasted.

Available skills:
{skill_info}

**Please use get_skill_description to see the usage of list_saved_subagents and run it as the first step to check if there's an existing saved subagent that can help with this question!**"""
    agent.messages.append({
        "role": "user",
        "content": initial_content
    })
    conv['messages'] = agent.messages

    # Return immediately so the frontend can show the question first,
    # then the frontend auto-calls /api/continue to start processing
    return jsonify({
        'conv_id': conv_id,
        'question': question,
        'status': 'running',
        'steps': [],
        'current_iteration': 0
    })

def process_step(conv_id):
    """Process a single step in the conversation."""
    conv = conversations.get(conv_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    # Check if cancelled
    if conv.get('status') == 'cancelled':
        return jsonify({
            'conv_id': conv_id,
            'question': conv['question'],
            'status': 'cancelled',
            'steps': conv['steps']
        })

    agent = conv['agent']
    if not agent:
        return jsonify({'error': 'Agent not initialized'}), 500

    conv['iteration'] += 1
    iteration = conv['iteration']

    # Call LLM
    system = SYSTEM_PROMPT
    result = call_llm(system, agent.messages)

    if not result["success"]:
        step_data = {
            'iteration': iteration,
            'type': 'error',
            'error': result.get('error'),
            'waiting_for_input': False
        }
        conv['steps'].append(step_data)
        return jsonify({
            'conv_id': conv_id,
            'question': conv['question'],
            'status': 'error',
            'error': result.get('error'),
            'steps': conv['steps']
        })

    response = result["response"]
    agent.log(f"\nLLM Response:\n{response[:2000]}...")

    # Detect hallucinated system responses (<response> tags)
    if '<response>' in response or '</response>' in response:
        agent.log("[HALLUCINATION DETECTED] LLM fabricated <response> tags.")
        resp_idx = response.find('<response>')
        if resp_idx == -1:
            resp_idx = response.find('</response>')
        clean_response = response[:resp_idx].rstrip() if resp_idx > 0 else ""
        agent.trajectory.append({
            "iteration": iteration,
            "type": "hallucination_detected",
            "content": response
        })
        if clean_response:
            agent.messages.append({"role": "assistant", "content": clean_response})
        else:
            agent.messages.append({"role": "assistant", "content": "(empty)"})
        agent.messages.append({
            "role": "user",
            "content": (
                "HALLUCINATION DETECTED: Your response contained a <response> tag. "
                "The <response> tag is RESERVED for the SYSTEM — you must NEVER write it yourself. "
                "You fabricated the system's output instead of waiting for the real result.\n\n"
                "Please retry: output ONLY your reasoning and ONE <action>...</action><params>...</params> block, "
                "then STOP. Do NOT predict or simulate what the system will return."
            )
        })
        conv['messages'] = agent.messages
        step_data = {
            "iteration": iteration,
            "type": "hallucination_detected",
            "content": response,
            "waiting_for_input": False
        }
        conv['steps'].append(step_data)
        return process_step(conv_id)

    # Store trajectory
    agent.trajectory.append({
        "iteration": iteration,
        "type": "llm_response",
        "content": response
    })

    # Also store in steps for frontend display
    step_data = {
        "iteration": iteration,
        "type": "llm_response",
        "content": response,
        "waiting_for_input": False
    }
    conv['steps'].append(step_data)

    # Parse action
    action = agent.parse_action(response)

    if action is None:
        agent.messages.append({"role": "assistant", "content": response})
        agent.messages.append({
            "role": "user",
            "content": "Please provide an action using XML tags, e.g.:\n<action>create_subagent</action>\n<params>\n{\"filename\": \"subagent.py\", \"code\": \"your code here\"}\n</params>"
        })
        conv['messages'] = agent.messages
        # Continue to next iteration
        return process_step(conv_id)

    # Handle JSON parse error
    if action.get("json_parse_error"):
        agent.log(f"\n[JSON Parse Error] {action['json_parse_error']}")
        agent.messages.append({"role": "assistant", "content": response})
        agent.messages.append({
            "role": "user",
            "content": f"ERROR: Failed to parse your <params> JSON: {action['json_parse_error']}\n\n"
                       f"This is likely caused by unescaped characters inside JSON string values. "
                       f"Please fix and retry. Remember:\n"
                       f"- Double quotes inside strings MUST be escaped: \\\"\n"
                       f"- Newlines must be escaped: \\n\n"
                       f"- Backslashes must be escaped: \\\\\n"
                       f"- IMPORTANT: You can only call ONE action at a time. Please check if you accidentally included multiple actions in your response."
        })
        conv['messages'] = agent.messages
        return process_step(conv_id)

    action_type = action.get("action")
    agent.log(f"\nAction: {action_type}")

    # Execute the action
    exec_result = agent.execute_action(action, conv['question'])

    # Check if this is a finish action
    is_finish = (action_type == "finish")

    if is_finish and exec_result.get("success"):
        final_answer = action.get("params", {}).get("answer", "") or exec_result.get("answer", "")
        agent.log(f"\n*** FINAL ANSWER: {final_answer} ***")

        # Wait for user confirmation before saving
        conv['status'] = 'waiting_confirm'
        conv['final_answer'] = final_answer
        conv['waiting_for_input'] = True
        conv['last_response'] = response
        conv['finish_params'] = action.get("params", {})

        step_data = {
            'iteration': iteration,
            'type': 'finish',
            'action': {'action': action_type},
            'result': exec_result,
            'final_answer': final_answer,
            'waiting_for_input': True
        }
        conv['steps'].append(step_data)
        conv['trajectory'] = agent.trajectory

        return jsonify({
            'conv_id': conv_id,
            'question': conv['question'],
            'status': 'waiting_confirm',
            'final_answer': final_answer,
            'steps': conv['steps'],
            'message': 'Please confirm: 1 = save & finish, 2 = discard & finish, other = continue improving'
        })

    elif is_finish and not exec_result.get("success"):
        agent.log(f"\nFinish failed: {exec_result.get('error', 'Unknown error')}")
        agent.trajectory.append({
            "iteration": iteration,
            "type": "action",
            "action": {"action": action_type},
            "result": exec_result
        })
        agent.messages.append({"role": "assistant", "content": response})
        agent.messages.append({
            "role": "user",
            "content": f"Error: {exec_result.get('error', 'Unknown error')}"
        })
        conv['messages'] = agent.messages
        conv['trajectory'] = agent.trajectory
        return process_step(conv_id)

    # Regular action result
    result_str = json.dumps(exec_result, ensure_ascii=False, indent=2)
    if len(result_str) > 10000:
        result_str = result_str[:10000] + "\n... [RESULT TRUNCATED] ..."

    agent.log(f"\nResult:\n{result_str[:2000]}...")

    agent.trajectory.append({
        "iteration": iteration,
        "type": "action",
        "action": {"action": action_type},
        "result": exec_result
    })

    agent.messages.append({"role": "assistant", "content": response})

    # Provide guidance based on action type
    if action_type == "get_skill_description":
        if exec_result.get("success"):
            desc = exec_result.get("description", "")
            skill_name = exec_result.get("skill_name", "")
            agent.messages.append({
                "role": "user",
                "content": f"Skill '{skill_name}' description:\n{desc}"
            })
        else:
            agent.messages.append({
                "role": "user",
                "content": f"Error getting skill description: {exec_result.get('error', '')}"
            })
    elif action_type == "create_subagent":
        agent.messages.append({
            "role": "user",
            "content": f"Result: {result_str}\n\nSubagent created. Use run_subagent to execute it."
        })
    elif action_type == "run_subagent":
        if exec_result.get("success"):
            answer = exec_result.get("answer", "")
            summary = exec_result.get("summary", "")
            output = f"ANSWER: {answer}\nSUMMARY: {summary}"
            agent.messages.append({
                "role": "user",
                "content": f"Subagent output:\n{output}\n\nCritically evaluate this result:\n1. Does the ANSWER fully satisfy ALL requirements of the original task?\n2. Does the SUMMARY contain red flags (vague language like 'may have', 'appears to', incomplete steps)?\n3. Is there concrete evidence of success, or just a claim?\nIf verified, use finish. If issues found, prefer using modify_subagent to fix the specific problem rather than rewriting from scratch."
            })
        else:
            agent.messages.append({
                "role": "user",
                "content": f"Subagent failed:\n{exec_result.get('error', '')}\n\nDiagnose the specific cause of failure from the error message above. Then prefer using modify_subagent to fix the specific broken part rather than rewriting the entire subagent."
            })
    elif action_type == "modify_subagent":
        if exec_result.get("success"):
            agent.messages.append({
                "role": "user",
                "content": f"Result: {result_str}\n\nSubagent code modified. Use run_subagent to test it."
            })
        else:
            agent.messages.append({
                "role": "user",
                "content": f"Modify failed: {exec_result.get('error', '')}\n\nMake sure old_content exactly matches text in your source code."
            })
    elif action_type == "list_saved_subagents":
        if exec_result.get("success"):
            skills = exec_result.get("skills", [])
            if skills:
                skill_names = ", ".join([s['name'] for s in skills])
                agent.messages.append({
                    "role": "user",
                    "content": f"Saved subagents: {skill_names}\n\nUse get_skill_description to view details, or run_subagent with skill_name parameter to run one."
                })
            else:
                agent.messages.append({
                    "role": "user",
                    "content": "No saved subagents found. Use create_subagent to create a new one."
                })
        else:
            agent.messages.append({
                "role": "user",
                "content": f"Error: {exec_result.get('error', '')}"
            })
    elif action_type == "view_subagent_code":
        if exec_result.get("success"):
            code = exec_result.get("code", "")
            entry_file = exec_result.get("entry_file", "")
            skill_name = exec_result.get("skill_name", "")
            agent.messages.append({
                "role": "user",
                "content": f"Source code of saved subagent '{skill_name}' (entry file: {entry_file}):\n```python\n{code}\n```"
            })
        else:
            agent.messages.append({
                "role": "user",
                "content": f"Error viewing subagent code: {exec_result.get('error', '')}"
            })
    else:
        agent.messages.append({
            "role": "user",
            "content": f"Result:\n{result_str}"
        })

    conv['messages'] = agent.messages
    conv['trajectory'] = agent.trajectory

    step_data = {
        'iteration': iteration,
        'type': 'action',
        'action': {'action': action_type},
        'result': exec_result,
        'waiting_for_input': False
    }
    conv['steps'].append(step_data)

    return jsonify({
        'conv_id': conv_id,
        'question': conv['question'],
        'status': 'running',
        'steps': conv['steps'],
        'current_iteration': iteration
    })

@app.route('/api/respond', methods=['POST'])
def respond_to_prompt():
    """Respond to continue after finish (user sends custom input to continue)."""
    data = request.json
    conv_id = data.get('conv_id')
    user_input = data.get('user_input', '').strip()

    conv = conversations.get(conv_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    # Handle waiting_confirm status - user is confirming finish
    if conv['status'] == 'waiting_confirm':
        agent = conv['agent']

        if user_input == '1':
            # Save and finish
            finish_params = conv.get('finish_params', {})
            agent._save_on_finish(finish_params, conv['final_answer'])

            # Save trajectory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            traj_file = os.path.join(agent.current_workspace, "trajectory.json")
            final_result = {
                "question": conv['question'],
                "final_answer": conv['final_answer'],
                "trajectory": conv.get('trajectory', []),
                "total_iterations": len([t for t in conv.get('trajectory', []) if t["type"] == "llm_response"]),
                "timestamp": timestamp
            }
            with open(traj_file, "w", encoding="utf-8") as f:
                json.dump(final_result, f, ensure_ascii=False, indent=2)

            conv['status'] = 'finished'

            step_data = {
                'iteration': conv['iteration'] + 1,
                'type': 'finish_confirmed',
                'user_input': user_input,
                'action': 'save_and_finish',
                'message': 'Saved and finished successfully'
            }
            conv['steps'].append(step_data)

            return jsonify({
                'conv_id': conv_id,
                'status': 'finished',
                'final_answer': conv['final_answer'],
                'steps': conv['steps'],
                'message': 'Saved and finished successfully'
            })

        elif user_input == '2':
            # Don't save and finish
            conv['status'] = 'finished'

            step_data = {
                'iteration': conv['iteration'] + 1,
                'type': 'finish_confirmed',
                'user_input': user_input,
                'action': 'discard_and_finish',
                'message': 'Finished without saving'
            }
            conv['steps'].append(step_data)

            return jsonify({
                'conv_id': conv_id,
                'status': 'finished',
                'final_answer': conv['final_answer'],
                'steps': conv['steps'],
                'message': 'Finished without saving'
            })

        else:
            # Custom input - continue with feedback
            conv['status'] = 'running'

            # Add user's feedback to messages
            agent.messages.append({"role": "assistant", "content": conv.get('last_response', '')})
            agent.messages.append({"role": "user", "content": user_input})

            step_data = {
                'iteration': conv['iteration'] + 1,
                'type': 'user_feedback',
                'user_input': user_input,
                'message': 'Continuing with user feedback'
            }
            conv['steps'].append(step_data)

            return process_step(conv_id)

    # Allow user to continue after finish (if they want to add more)
    if conv['status'] == 'finished':
        conv['status'] = 'running'
        agent = conv['agent']
        if agent and user_input:
            agent.messages.append({"role": "user", "content": user_input})
            return process_step(conv_id)

    # Cancelled status - allow user to send input to restart
    if conv['status'] == 'cancelled':
        # Create new agent for fresh start
        agent = create_agent()
        conv['agent'] = agent
        conv['iteration'] = 0
        conv['steps'] = []
        conv['trajectory'] = []

        # Reinitialize agent state
        agent.trajectory = []
        agent.messages = []
        agent.current_skills = []
        agent.viewed_skill_descriptions = set()
        agent.viewed_subagent_codes = set()
        agent.modified_skills = {}
        agent.correct_answer = None

        agent.current_workspace = os.path.join(
            PARENT_DIR, "workspace", conv['timestamp'], "q0"
        )
        os.makedirs(agent.current_workspace, exist_ok=True)

        # Get all available skills
        all_skills = list_all_skills()
        skill_info = "\n".join([f"- {s['name']} ({s['type']})" for s in all_skills])

        initial_content = f"""Question: {conv['question']}

You are a deep research agent. When you create subagents to help solve this problem, they must be GENERAL - your subagent should NOT contain any content specific to this question only. The subagent you create should be able to help with general deep research tasks, not just this specific one. For example, if you create a subagent to help search for information, it should take any research topic as input and work independently - it should NOT have hardcoded search queries or topic-specific logic.

CRITICAL RULE: Each response must contain AT MOST ONE <action>...</action><params>...</params> block, then STOP IMMEDIATELY.
- NEVER write <response> tags — they are RESERVED for the system. If you write <response> yourself, it is hallucination and will be rejected.
- NEVER predict, simulate, or fabricate what the system will return — wait for the actual result in the next message.
- NEVER chain multiple actions in one response — only the first one will be executed, the rest are wasted.

Available skills:
{skill_info}

**Please use get_skill_description to see the usage of list_saved_subagents and run it as the first step to check if there's an existing saved subagent that can help with this question!**"""
        agent.messages.append({
            "role": "user",
            "content": initial_content
        })

        if user_input:
            agent.messages.append({"role": "user", "content": user_input})

        conv['status'] = 'running'
        return process_step(conv_id)

    if conv['status'] != 'running':
        return jsonify({'error': 'Conversation not in running state'}), 400

    agent = conv['agent']

    # Check user input - now we use the original logic: 1=save, 2=discard
    # But since we auto-save now, these are less relevant. However, keep for compatibility
    if user_input == '1':
        # Save and finish (already saved, just confirm)
        conv['status'] = 'finished'

        step_data = {
            'iteration': conv['iteration'] + 1,
            'type': 'finish_confirmed',
            'user_input': user_input,
            'action': 'save_and_finish',
            'message': 'Saved and finished successfully'
        }
        conv['steps'].append(step_data)

        return jsonify({
            'conv_id': conv_id,
            'status': 'finished',
            'final_answer': conv['final_answer'],
            'steps': conv['steps'],
            'message': 'Saved and finished successfully'
        })

    elif user_input == '2':
        # Don't save and finish
        conv['status'] = 'finished'
        conv['waiting_for_input'] = False

        step_data = {
            'iteration': conv['iteration'] + 1,
            'type': 'finish_confirmed',
            'user_input': user_input,
            'action': 'discard_and_finish',
            'message': 'Discarded and finished'
        }
        conv['steps'].append(step_data)

        return jsonify({
            'conv_id': conv_id,
            'status': 'finished',
            'final_answer': conv['final_answer'],
            'steps': conv['steps'],
            'message': 'Finished without saving'
        })

    else:
        # Custom input - continue with instruction
        conv['status'] = 'running'
        conv['waiting_for_input'] = False

        # Add user's custom input to messages
        agent.messages.append({"role": "assistant", "content": conv['last_response']})
        agent.messages.append({"role": "user", "content": user_input})

        step_data = {
            'iteration': conv['iteration'] + 1,
            'type': 'user_continue',
            'user_input': user_input,
            'message': 'Continuing with user instruction'
        }
        conv['steps'].append(step_data)

        return process_step(conv_id)

@app.route('/api/continue', methods=['POST'])
def continue_running():
    """Continue running the agent after a step."""
    data = request.json
    conv_id = data.get('conv_id')

    conv = conversations.get(conv_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    if conv['status'] == 'finished':
        return jsonify({'error': 'Conversation already finished'}), 400

    return process_step(conv_id)

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    """Get list of all conversations."""
    conv_list = []
    for conv_id, conv in conversations.items():
        conv_list.append({
            'id': conv['id'],
            'question': conv['question'][:100] + '...' if len(conv['question']) > 100 else conv['question'],
            'created_at': conv['created_at'],
            'status': conv['status'],
            'final_answer': conv.get('final_answer'),
            'steps_count': len(conv['steps'])
        })
    # Sort by created_at descending
    conv_list.sort(key=lambda x: x['created_at'], reverse=True)
    return jsonify({'conversations': conv_list})

@app.route('/api/conversation/<conv_id>', methods=['GET'])
def get_conversation(conv_id):
    """Get a specific conversation."""
    conv = conversations.get(conv_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    return jsonify({
        'id': conv['id'],
        'question': conv['question'],
        'created_at': conv['created_at'],
        'status': conv['status'],
        'steps': conv['steps'],
        'final_answer': conv.get('final_answer'),
        'trajectory': conv.get('trajectory', [])
    })

@app.route('/api/delete/<conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    """Delete a conversation."""
    if conv_id in conversations:
        del conversations[conv_id]
        return jsonify({'success': True})
    return jsonify({'error': 'Conversation not found'}), 404

@app.route('/api/cancel/<conv_id>', methods=['POST'])
def cancel_conversation(conv_id):
    """Cancel/stop a running conversation."""
    conv = conversations.get(conv_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    conv['status'] = 'cancelled'
    conv['waiting_for_input'] = False

    return jsonify({'success': True, 'status': 'cancelled'})

@app.route('/api/subagents', methods=['GET'])
def list_subagents():
    """List all saved subagent skills with metadata."""
    from skills_utils import list_subagent_skills, SUBAGENT_SKILLS_DIR
    skills = list_subagent_skills()
    result = []
    for s in skills:
        skill_dir = os.path.join(SUBAGENT_SKILLS_DIR, s['directory'])
        skill_md_path = os.path.join(skill_dir, 'SKILL.md')
        result.append({
            'name': s['name'],
            'description': s['description'],
            'directory': s['directory'],
            'skill_md_path': skill_md_path
        })
    return jsonify({'subagents': result})

@app.route('/api/subagent/<name>/skill_md', methods=['GET'])
def get_subagent_skill_md(name):
    """Get the SKILL.md content for a subagent."""
    from skills_utils import SUBAGENT_SKILLS_DIR, parse_skill_md
    # Find by name or directory
    if not os.path.exists(SUBAGENT_SKILLS_DIR):
        return jsonify({'error': 'No subagents directory'}), 404

    for dirname in os.listdir(SUBAGENT_SKILLS_DIR):
        skill_dir = os.path.join(SUBAGENT_SKILLS_DIR, dirname)
        if not os.path.isdir(skill_dir):
            continue
        skill_md = os.path.join(skill_dir, 'SKILL.md')
        if not os.path.exists(skill_md):
            continue
        parsed = parse_skill_md(skill_md)
        if parsed and (parsed['name'] == name or dirname == name):
            with open(skill_md, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({'name': parsed['name'], 'content': content})

    return jsonify({'error': f'Subagent not found: {name}'}), 404

@app.route('/api/workspace/<conv_id>', methods=['GET'])
def get_workspace(conv_id):
    """Get workspace contents for a conversation."""
    conv = conversations.get(conv_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    timestamp = conv.get('timestamp')
    if not timestamp:
        return jsonify({'error': 'No workspace for this conversation'}), 404

    workspace_path = os.path.join(PARENT_DIR, "workspace", timestamp, "q0")
    if not os.path.exists(workspace_path):
        return jsonify({'error': 'Workspace not found'}), 404

    files = []
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}

    for root, dirs, filenames in os.walk(workspace_path):
        for filename in filenames:
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, workspace_path)
            is_image = any(filename.lower().endswith(ext) for ext in image_extensions)

            file_info = {
                'name': filename,
                'path': rel_path,
                'type': 'image' if is_image else 'file',
                'size': os.path.getsize(filepath)
            }
            files.append(file_info)

    return jsonify({
        'workspace_path': workspace_path,
        'files': files
    })

@app.route('/api/workspace/<conv_id>/file', methods=['GET'])
def get_workspace_file(conv_id):
    """Get a specific file from workspace."""
    from flask import send_file, send_from_directory
    import base64

    conv = conversations.get(conv_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404

    timestamp = conv.get('timestamp')
    if not timestamp:
        return jsonify({'error': 'No workspace for this conversation'}), 404

    workspace_path = os.path.join(PARENT_DIR, "workspace", timestamp, "q0")
    filepath = request.args.get('path', '')

    full_path = os.path.join(workspace_path, filepath)
    if not os.path.exists(full_path):
        return jsonify({'error': 'File not found'}), 404

    # Check if it's an image
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
    is_image = any(full_path.lower().endswith(ext) for ext in image_extensions)

    if is_image:
        with open(full_path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('utf-8')
        ext = os.path.splitext(full_path)[1].lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp'
        }
        mime = mime_types.get(ext, 'image/png')
        return jsonify({
            'type': 'image',
            'data': f'data:{mime};base64,{data}',
            'filename': os.path.basename(full_path)
        })
    else:
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return jsonify({
            'type': 'file',
            'content': content[:50000],  # Limit to 50k chars
            'filename': os.path.basename(full_path)
        })

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Meta-Agent Web Interface")
    parser.add_argument('--port', type=int, default=5000, help='Port to run the server on')
    args = parser.parse_args()

    import logging
    logging.basicConfig(level=logging.INFO)

    print("Starting Meta-Agent Web Interface...")
    print(f"Open http://localhost:{args.port} in your browser")
    app.run(debug=False, port=args.port, use_reloader=False, threaded=False)