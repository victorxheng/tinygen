# tinygen
Tiny version of Codegen

# Installation

Recommend using a venv for python packages.

Remember to add a .env file with ANTHROPIC_API_KEY="your_key_here".

You can obtain your API key by signing up here: https://console.anthropic.com/


# How it works

Tinygen deploys a fastAPI server that takes in a repoURL and a prompt. It then is able to generate a diff output
that modifies the code base based on the prompt. 

See the technologies section below for more details.

# Hitting the API

The API contains two parameters: repoURL, which is the link of the repo, and prompt, which is the change you want to make. The end point is on here: https://tinygen-jgbn.onrender.com/analyze/

You can use postman or cURL to send a POST request with a json body: 
{"repoUrl": "https://github.com/jayhack/llm.sh", "prompt": "The program doesnt output anything in windows 10"}

Here is an example of a cURL request:

curl -X POST https://tinygen-jgbn.onrender.com/analyze/
   -H 'Content-Type: application/json'
   -d '{"repoUrl": "https://github.com/jayhack/llm.sh", "prompt": "The program doesnt output anything in windows 10"}'


It takes a while to get a response, as we have a multi-step process.

# Technologies

We utilize Anthropic's latest Claude-3 Opus model due to significant improvements in code writing abilities over GPT-4.

We also use a multi-pass system to build context for the AI to more accurately write its diff:

1. First, we traverse the file system and create a sheet containing the paths of each file and its contents
2. Next, we use Claude to analyze the files, draw connections, and determine where changes should be made
3. Next, Claude then uses its analysis results to compile a diff bash
4. Finally, Claude verifies the diff bash against everything above and makes any necessary changes

NOTE: The current API endpoint uses sonnet, not opus, because opus is more expensive, slower, and overloads more.

However, Opus has been proven to be a more powerful model for code generation.

You can change the model to opus locally by uncommenting # model = "claude-3-opus-20240229"


# Improvements

Claude 3 Opus's context window is 200k, which caps out at around 20,000 lines of code.
For code bases larger than that, tinygen won't be able to fit the entire code base in a single context window.

The solution? Walk through each file one by one and build out a reference sheet that allows the AI to understand the code base within the context window.

1. The first walk through creates a context string explaining the code base and each file's depencies on other files at each part in the heirarchy.
2. Then, the AI brainstorms where the changes should be made based on what it learned through analysis.
3. Next, our second walk through is where it determines at each step whether diff changes should be made or not, and adds the diff to the diff file
4. Finally, on the third walk through, it verifies against the entire diff file whether that change was appropriate. It then can rewrite it.

This process allows for the abstraction of each file and the simplification of the context when it comes to the code itself.

We traverse one file at a time rather than inserting in the entire code base.

For even larger code bases, function calling will be required to perform searches, and some more abstraction will be involved such as hiding the implementation of functions unless requested.

