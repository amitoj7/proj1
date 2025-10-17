# Utility functions for the LLM Code Deployment Agent
import os
import base64
import requests
import time
import threading
from github import Github

def process_request(data):
    """
    This function will be called in a separate thread to process the request.
    """
    task_id = data.get('task')
    brief = data.get('brief')
    attachments = data.get('attachments', [])
    evaluation_url = data.get('evaluation_url')
    nonce = data.get('nonce')
    round_num = data.get('round')
    email = data.get('email')


    generate_app(brief, attachments, task_id, round_num)

    g = Github(os.environ.get('GITHUB_TOKEN'))
    user = g.get_user()
    repo_name = f"task-{task_id}"

    if round_num == 1:
        repo = create_repo(task_id)
    else:
        repo = user.get_repo(repo_name)

    commit = upload_files_to_repo(task_id, repo, round_num)
    pages_url = enable_pages(repo)

    payload = {
        "email": email,
        "task": task_id,
        "round": round_num,
        "nonce": nonce,
        "repo_url": repo.html_url,
        "commit_sha": commit.sha,
        "pages_url": pages_url,
        "evaluation_url": evaluation_url
    }
    notify_evaluation(payload)

import openai
import json

def generate_app(brief, attachments, task_id, round_num):
    """
    Generates the application files based on the brief and attachments.
    """
    task_dir = f"task-{task_id}"
    os.makedirs(task_dir, exist_ok=True)

    # Handle attachments
    for attachment in attachments:
        file_name = attachment.get('name')
        data_uri = attachment.get('url')
        if file_name and data_uri:
            header, encoded = data_uri.split(",", 1)
            data = base64.b64decode(encoded)
            with open(os.path.join(task_dir, file_name), "wb") as f:
                f.write(data)

    prompt = f"""
You are an expert web developer. Your task is to build a single-page web application based on the following brief:

**Brief:** {brief}

**Instructions:**
1.  Create a single `index.html` file.
2.  You can use HTML, CSS, and JavaScript.
3.  If CSS or JavaScript is needed, embed it directly into the `index.html` file.
4.  The application should be self-contained in this single file.
5.  Do not use any external libraries unless specified in the brief.
6.  The output should be a JSON object with a single key "html" and the value as the complete HTML code.
"""
    if round_num > 1:
        with open(os.path.join(task_dir, "index.html"), "r") as f:
            existing_html = f.read()
        prompt += f"\n**Existing HTML (for revision):**\n```html\n{existing_html}\n```"


    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a web developer assistant."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )

    try:
        output = json.loads(response.choices[0].message.content)
        html_content = output.get("html", "")
    except (json.JSONDecodeError, KeyError):
        html_content = "<html><body>Error generating content.</body></html>"


    with open(os.path.join(task_dir, "index.html"), "w") as f:
        f.write(html_content)

def create_repo(task_id):
    """
    Creates a new public repository on GitHub.
    """
    g = Github(os.environ.get('GITHUB_TOKEN'))
    user = g.get_user()
    repo_name = f"task-{task_id}"
    try:
        repo = user.create_repo(repo_name, private=False)
        return repo
    except Exception as e:
        # If repo exists, get the repo object
        if e.status == 422: # Unprocessable Entity (repo already exists)
            return user.get_repo(repo_name)
        else:
            raise e

def upload_files_to_repo(task_id, repo, round_num):
    """
    Commits and pushes the generated application files to the repository.
    """
    task_dir = f"task-{task_id}"

    if round_num == 1:
        # Create LICENSE
        repo.create_file("LICENSE", "Add LICENSE", "MIT License", branch="main")

        # Create README.md
        readme_content = f"""
# {task_id}

## Summary
This project is an auto-generated web application based on a provided brief.

## Setup
To run this application, simply open the `index.html` file in your web browser.

## Code Explanation
The `index.html` file contains the entire application, including the HTML structure, CSS styling, and JavaScript logic.

## License
This project is licensed under the MIT License.
"""
        repo.create_file("README.md", "Add README", readme_content, branch="main")


    for file_name in os.listdir(task_dir):
        with open(os.path.join(task_dir, file_name), 'rb') as file:
            content = file.read()

        try:
            # Try to get the file to see if it exists
            existing_file = repo.get_contents(file_name, ref="main")
            repo.update_file(existing_file.path, f"Update {file_name}", content, existing_file.sha, branch="main")
        except:
            # If it doesn't exist, create it
            repo.create_file(file_name, f"Add {file_name}", content, branch="main")

    return repo.get_commits()[0]

def enable_pages(repo):
    """
    Enables GitHub Pages for the repository.
    """
    # Note: As of my last update, PyGithub does not have a direct method
    # to enable GitHub Pages for a repository. The following is a workaround
    # that uses the requests library to call the GitHub API directly.

    headers = {
        "Authorization": f"token {os.environ.get('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github.switcheroo-preview+json"
    }
    data = {"source": {"branch": "main", "path": "/"}}
    url = f"https://api.github.com/repos/{repo.full_name}/pages"

    response = requests.post(url, json=data, headers=headers)

    if response.status_code == 201:
        # Wait a bit for pages to be deployed
        time.sleep(10)
        return response.json().get('html_url')
    else:
        # Fallback for if it's already enabled
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get('html_url')

    return None

def notify_evaluation(payload):
    """
    Notifies the evaluation service.
    """
    url = payload.get("evaluation_url")
    if not url:
        return

    del payload["evaluation_url"] # a bit of a hack, but works

    delay = 1
    for i in range(4): # Try up to 4 times
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                print("Evaluation notification sent successfully.")
                return
        except requests.exceptions.RequestException as e:
            print(f"Error sending evaluation notification: {e}")

        time.sleep(delay)
        delay *= 2