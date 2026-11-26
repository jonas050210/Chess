# Run Chess Bot on Windows with PowerShell

These instructions assume the improvements have been merged into `main`.

## 1. Install Python and Git

Install Python 3.10 or newer from <https://www.python.org/downloads/windows/> and Git for Windows. In the Python installer, enable the Python launcher and Tcl/Tk support. Then open a **new** PowerShell window and check:

```powershell
py -0p
py -3 -m tkinter
git --version
```

The Tkinter command should open a small test window; close it to continue.

## 2. Clone and install

```powershell
Set-Location $HOME
git clone https://github.com/jonas050210/Chess.git
Set-Location $HOME\Chess
py -3 -m venv .venv
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, allow it **for this PowerShell process only**, then activate:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Install the runtime dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 3. Play

### Three native windows (recommended)

```powershell
python main.py
```

`main.py` starts the local server automatically. Use `python main.py --low` on a low-memory laptop.

### Browser UI only

In one PowerShell window:

```powershell
Set-Location $HOME\Chess
.\.venv\Scripts\Activate.ps1
python server.py
```

Open <http://127.0.0.1:8000> in your browser. Leave that PowerShell window open while playing; press `Ctrl+C` there to stop the server.

If port 8000 is already in use, use the same port in both processes. In the first PowerShell window, start the server:

```powershell
Set-Location $HOME\Chess
.\.venv\Scripts\Activate.ps1
$env:PORT = "8001"
$env:CHESS_PORT = "8001"
python server.py
```

Open a second PowerShell window for the native UI:

```powershell
Set-Location $HOME\Chess
.\.venv\Scripts\Activate.ps1
$env:CHESS_PORT = "8001"
python main.py
```

The server binds to loopback by default. Do not set `CHESS_HOST` to `0.0.0.0` unless you intentionally want network access and understand that the API has no authentication.

## 4. Verify the install

```powershell
$env:CHESS_LOW_RAM = "1"
python -m unittest discover -s tests -v
python -m compileall -q ai server.py main.py tools tests
Remove-Item Env:CHESS_LOW_RAM
```

The tests do not require a graphical desktop. GitHub Actions also runs them on Python 3.10 and 3.12.

## 5. Training (CPU smoke / CPU training)

First inspect the plan; this does not train a model:

```powershell
python ai/train_cli.py --dry-run
```

A short CPU smoke run writes a candidate and does not promote it:

```powershell
python ai/train_cli.py --preset smoke --smoke-games 1 --smoke-sims 2 --max-plies 20 --smoke-epochs 1 --max-seconds 60 --no-promote
```

For a longer CPU run, still protecting the active model:

```powershell
python ai/train_cli.py --preset cpu --max-seconds 600 --no-promote
```

To attempt the Arena promotion gate, omit `--no-promote` and provide a sufficiently long evaluation, for example:

```powershell
python ai/train_cli.py --preset cpu --max-seconds 1800 --eval-games 32 --eval-sims 25
```

The promotion gate requires at least 12 paired games and conservative confidence bounds. Passing it is not proof of general chess strength. CUDA/GPU training is documented for Ubuntu; the Windows commands above use CPU training.

## 6. Stop / clean up

Close the Tk windows, or press `Ctrl+C` in the server window when running browser mode. To leave the virtual environment:

```powershell
deactivate
```
