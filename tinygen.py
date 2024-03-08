import os
import tempfile
import logging
from fastapi import FastAPI, HTTPException
from git import Repo
import anthropic
import dotenv
from pydantic import BaseModel


dotenv.load_dotenv()

app = FastAPI()
client = anthropic.Anthropic()

# YOU CAN SWITCH BETWEEN CLAUDE 3 SONNET AND OPUS
# Opus does overload more and is slower + more expensive, but more powerful
model = "claude-3-sonnet-20240229"
# model = "claude-3-opus-20240229"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

'''
IMPROVING THE AI SYSTEM FOR LARGER CODE BASES: Proposal
1. the first walk through creates a context string explaining the code base and depencies on other files at each part in the heirarchy.
2. then, the AI brainstorms where the changes should be made based on what it learned through analysis.
3. Finally, our second walk through is where it determines at each step whether diff changes should be made or not, and adds the diff to the diff file
4. On the third walk through, it verifies against the entire diff file whether that change was appropriate. It then can rewrite it.

This process allows for the abstraction of each file and the simplification of the context when it comes to the code itself.
We traverse one file at a time rather than inserting in the entire code base.

For even larger code bases, function calling will be required to perform searches.

'''


simple_code_analysis_system = f"""
You are an expert programmer tasked with analyzing and explaining what a code base does.

Your job is to identify and explain a code base, highlight the file structure and what each file does, how they are dependent, and the functions that lie in each file.

Based on a prompt, you will identify possible places and changes that should be made to the code base and write out the changes in clear detail.

The changes that must be made must be simple and as concise as possible with the bare minimum changes to satisfy the prompt. You are not allowed to go above and beyond and must only make minimal changes.
"""

simple_diff_generation_system = f"""
You are an expert programmer tasked with analyzing github repositories to identify problems address or improvements to make. 
As an expert programmer, you are very good at identify necessary changes in the code base based on what a user is asking. The user will ask a question regarding the code base. Your task is to figure out the issue and make the necessary changes.
Your output is in the format of a diff file wrapped by triple back ticks (```) labeled as bash, for example, the diff file should look like this:

```bash
diff --git a/src/main.py b/src/main.py
index 58d38b6..23b0827 100644
--- a/src/main.py
+++ b/src/main.py
@@ -19,7 +19,10 @@ def run_bash_file_from_string(s: str):
     '''Runs a bash script from a string'''
     with open('temp.sh', 'w') as f:
         f.write(s)
-    os.system('bash temp.sh')
+    if os.name == 'nt':  # Windows systems
+        os.system('powershell.exe .\\temp.sh')
+    else:  # Unix/Linux systems
+        os.system('bash temp.sh')
     os.remove('temp.sh')
```


Notice the following in the diff file that you must strictly adhere to:
The bash code is wrapped in triple back ticks, with the first set having the word bash next to it: ```bash
Starts with the diff command with the file paths. 
The code base provided by the user will contain file paths for the code file to be included, starting with the file to change, from a/[file_name] to b/[file_name].
Next, contains the index hash as well as the file to be edited, showing the removal of the a/ file and the addition of the b/ file
Next, includes each of the changes as well as the header for the location of the change and the bash.file

Use your experience to write unified git files for our github bash commands.file

Remember to do it based on the code base and the user prompt. Look through each file and determine changes to be made. At the very end, include the full code base. Do not write code anywhere else.

Also remember that every part of the bash file is correct. This includes every line number, every hash, every change, every file path, etc.

You started by first brainstorming changes to be made, how files are connected, and create a plan as to how you plan on tackling the changes based on your analysis expertise.

Finally, write the diff file based on your in-depth analysis of the code.

Your changes must be as minimal and concise as possible and do the bare minimum to satisfy the prompt.
"""

final_step_message = f"""
Look through all the code and the suggested changes one more time and verify that the diff file is perfect with 0 flaws and 0 issues. 
This means no headers are off, everything is formatted correctly based on your expert diff writing experience, and all changes will fulfill the user prompt.
If there are no errors, do not change the diff file at all. Simply rewrite it in the correct format with no other text.
If there are errors, make sure that you can make these changes when you rewrite the diff to make sure that it is perfect.
Remember to only have the diff surrounded by triple back ticks in your final output with no other text. This means you start with "```bash" and end with "```" and no other text and no other code at all.
Make sure that the diff is the bare minimum for the prompt.

User prompt again: 
"""

test_prompt = r"""
# The program doesn't output anything in windows 10

(base) C:\Users\off99\Documents\Code\>llm list files in current dir; windows
/ Querying GPT-3200
───────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────
       │ File: temp.sh
───────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────
   1   │
   2   │ dir
   3   │ ```
───────┴────────────────────────────────────────────────────────────────────────────────────────────────────────────────
>> Do you want to run this program? [Y/n] y

Running...


(base) C:\Users\off99\Documents\Code\>
Notice that there is no output. Is this supposed to work on Windows also?
Also it might be great if the script detects which OS or shell I'm using and try to use the appropriate command e.g. dir instead of ls because I don't want to be adding windows after every prompt.                     
"""

def add_context(code: str, path: str) -> str:
    """
    Returns the format for adding to the code context string.
    Args:
        system (str): The code to add
        path (str): the path to add

    Returns:
        str: The added message.
    """
    return f'''
_____  

REPO FILE PATH: 
{path}

FILE CONTENT:
```
{code}
```

____

'''

def add_content(context: str, prompt: str) -> str:
    """
    Returns the format for adding content to the user 
    Args:
        context (str): The context to add
        prompt (str): The prompt to add

    Returns:
        str: The added message.
    """
    return f"""
CODE BASE:

{context}


_________________

USER PROMPT
Analyze changes to be made to this code base based on this prompt:
{prompt}
"""


def send_message(system: str, messages) -> str:
    """
    Send a message to the selected Claude-3 model through Anthropic with streaming.
    Args:
        system (str): The system string
        messages: An array containing all the past messages so far.

    Returns:
        str: The Claude-3 generated message.
    """

    reply = ''
    with client.messages.stream(
        model=model,
        max_tokens=4096,
        temperature=0.0,
        system=system,
        messages=messages) as stream:
            for text in stream.text_stream:
                reply += text
                print(text, end="", flush=True)
    print()
    return reply



    
def clone_repository(repo_url: str, temp_dir: str) -> Repo:
    """
    Clones the specified GitHub repository into a temporary directory.

    Args:
        repo_url (str): The URL of the GitHub repository to clone.
        temp_dir (str): The path to the temporary directory where the repository will be cloned.

    Returns:
        Repo: The cloned repository object.

    Raises:
        HTTPException: If an error occurs during repository cloning.
    """
    try:
        repo = Repo.clone_from(repo_url, temp_dir)
        return repo
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to clone repository: {str(e)}")



def analyze_repo(repo_url: str, prompt: str) -> str:
    """
    Clones the specified GitHub repository, analyzes the code using the Claude 3 API based on the provided prompt,
    generates a unified diff representing the suggested changes, and returns the diff as a string.
    Also does multiple pass-throughs to ensure thorough analysis and accurate results.

    Args:
        repo_url (str): The URL of the GitHub repository to analyze.
        prompt (str): The prompt to use for analyzing the code.

    Returns:
        str: The unified diff representing the suggested changes.

    Raises:
        HTTPException: If an error occurs during repository cloning, API communication, or analysis.
    """
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = clone_repository(repo_url, temp_dir)

            context = ""
            original_root = next(os.walk(temp_dir))[0]

            for root, dirs, files in os.walk(temp_dir):
                files = [f for f in files if not f[0] == '.']
                dirs[:] = [d for d in dirs if not d[0] == '.']
                for file in files:
                    git_file_path = os.path.join(root.split(original_root)[1], file)
                    file_path = os.path.join(root, file)
                    if file.endswith(".zip") or not os.access(file_path, os.R_OK):
                        continue
                    try:
                        with open(file_path, 'r') as file:
                            content = file.read()
                            context = context + add_context(content, git_file_path)
                    except Exception as e:
                        print(f"Error reading {file_path}: {e}")
            
            history = [
                    {
                        "role": "user", 
                        "content": add_content(context, prompt)
                    }
                ]   
            print(context)
            
            # have it first add a breakdown explaining the code file and the possible changes that should be made
            reply = send_message(simple_code_analysis_system, history)
            history.append({"role":"assistant", "content": reply})            
            history.append({"role":"user", "content": f"Now, generate the diff file based on what should be changed. Once again, the user prompt is: {prompt}"})
            
            # next, have it analyze the breakdown of the code base to produce a diff
            reply = send_message(simple_diff_generation_system, history)
            
            # on the final step, make it verify the diff file then format it properly and save
            history.append({"role":"assistant", "content": reply})            
            history.append({"role":"user", "content": final_step_message + prompt})            
            reply = send_message(simple_diff_generation_system, history)

            # return the code formatted between the bash ticks
            return reply.split("```bash\n")[1].split("\n```")[0]
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("An unexpected error occurred.")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


def test():
    diff = analyze_repo("https://github.com/jayhack/llm.sh",test_prompt)
    print("\n\nDIFF: \n\n" + diff)

if __name__ == "__main__":
    test()


# using fast api
    
class Payload(BaseModel):
    repoUrl: str # project spec said camelCase
    prompt: str


@app.post("/analyze/")
async def create_item(payload: Payload) -> str:
    diff = analyze_repo(payload.repoUrl, payload.prompt)
    return diff