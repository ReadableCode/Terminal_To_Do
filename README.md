# Terminal_To_Do

## Set up with Pyenv

### Windows pyenv setup

- Use winget to install pyenv-win

```bash
winget install --id=pyenv-win.pyenv-win
```

- Install python 3.12

```bash
pyenv install 3.12.4
```

- Switch to this version of python globally

```bash
pyenv global 3.12.4
```

- Switch to this version of python locally
  
```bash
pyenv local 3.12.4
```

- Activate shell with pyenv
  
```bash
pyenv shell 3.12.4
```

- Use pipenv to install dependencies

```bash
pip install pipenv
pipenv install

```

- To Activate or Source the environment and not have to prepend each command with pipenv:

  On Linux:

  ```bash
  source $(pipenv --venv)/bin/activate
  ```
  
  On Windows (Powershell):

  ```bash
  & "$(pipenv --venv)\Scripts\activate.ps1"
  ```

- To Deactivate:

  ```bash
  deactivate
  ```
