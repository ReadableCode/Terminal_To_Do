# Terminal_To_Do

## Set up with Pyenv

### Windows pyenv setup

- Use chocolotey to install pyenv-win

```bash
choco install pyenv-win
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

- Install dependencies into this version of python

```bash
python3 -m pip install -r requirements.txt
```
