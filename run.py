"""
Meta-Agent: An agent that creates, runs, and optimizes question-specific subagents.
Now with Skills support - all actions are unified as skills.
"""

import json
import os
from datetime import datetime

# Get absolute paths based on script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

from meta_agent import MetaAgent

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Meta-Agent for solving questions")
    parser.add_argument("--question-file", default="data/questions/questions_round1.jsonl", help="Path to question file")
    parser.add_argument("--no-save", action="store_true", default=False,
                        help="Do not save subagent on finish")
    parser.add_argument("--human-confirm", action="store_true", default=False,
                        help="Require human confirmation after each LLM response")

    args = parser.parse_args()

    question_path = args.question_file
    if not os.path.isabs(question_path):
        question_path = os.path.join(SCRIPT_DIR, question_path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(question_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            data = json.loads(line.strip())
            question = data["question"]
            correct_answer = data.get("answer", None)

            print("="*80)
            print("QUESTION:")
            print(question)
            print("="*80)

            agent = MetaAgent(
                verbose=True,
                save_on_finish=not args.no_save,
                human_confirm=args.human_confirm
            )

            restart = True
            while restart:
                result = agent.run(question, timestamp, i, correct_answer)
                # Check if user chose to restart the same question
                if result.get('final_answer') == "[Restarted by user]":
                    # Recreate agent for fresh start
                    agent = MetaAgent(
                        verbose=True,
                        save_on_finish=not args.no_save,
                        human_confirm=args.human_confirm
                    )
                    continue  # Restart same question
                restart = False

            # Check if user chose to skip to next question
            if result.get('final_answer') == "[Skipped by user]":
                continue

            print("\n" + "="*80)
            print("FINAL RESULT")
            print("="*80)
            print(f"Answer: {result['final_answer']}")
            print(f"Total iterations: {result['total_iterations']}")


if __name__ == "__main__":
    main()
