# AI Agents with Smolagents
In this directory some tools, callbacks abstractions are created for makeing the GUI based setup work with the CodeAgent, based off the [Smolagents](https://github.com/huggingface/smolagents) package.
Read more about Smolagents [here](https://huggingface.co/docs/smolagents/en/index).

```sh
📦agent
 ┣ 📂tools
 ┃ ┣ 📂models                               # Directory for local models to use as tool/callback/part of the agent workflow
 ┃ ┃ ┣ 📂gui_actor
 ┃ ┃ ┃ ┣ 📜README.md
 ┃ ┃ ┃ ┣ 📜__init__.py
 ┃ ┃ ┃ ┣ 📜constants.py
 ┃ ┃ ┃ ┣ 📜dataset.py
 ┃ ┃ ┃ ┣ 📜inference.py
 ┃ ┃ ┃ ┣ 📜modeling.py
 ┃ ┃ ┃ ┣ 📜modeling_qwen25vl.py
 ┃ ┃ ┃ ┣ 📜trainer.py
 ┃ ┃ ┃ ┗ 📜utils.py
 ┃ ┃ ┗ 📂images
 ┃ ┃ ┃ ┣ 📂prediction
 ┃ ┃ ┃ ┃ ┗ 📜prediction_ubuntu-desktop.png
 ┃ ┃ ┃ ┣ 📜jupyter-lab.png
 ┃ ┃ ┃ ┗ 📜ubuntu-desktop.png
 ┃ ┣ 📜callbacks.py                         # Callbacks module
 ┃ ┣ 📜gui.py                               # Start of a GUI module that can be used in the workflow (using gui-actor)  # TO-DO
 ┃ ┗ 📜rag.py                               # Example of a RAG module that can be used in the workflow                  # TO-DO
 ┣ 📜README.md
 ┣ 📜__init__.py
 ┣ 📜executor.py                            # Module for the Sandbox Executor, this is for the the connection with the Jupyter Kernel gateway, works in the GUI setup
 ┣ 📜logger.py                              # Adaption of the Smolagents's AgentLogger, this one makes it possible to output the logs as html.
 ┗ 📜sandbox_agent.py                       # Adaption of the Smolagents's CodeAgent, this specifically overwrites some methods so it works in this GUI based setup.
```
