# Collimator Creator

Desktop GUI application for generating and exporting collimator CAD parts.

## Requirements

- macOS/Linux/Windows desktop with a graphical display
- [Conda](https://docs.conda.io/en/latest/) (Miniconda or Anaconda)

## Install

From the project root:

```bash
conda env create -f environment.yml
conda activate cc_env
```

## Run

```bash
python CC_app.py
```

## Update after `git pull`

```bash
conda env update -f environment.yml --prune
conda activate cc_env
```

## Smoke checks (optional)

Run tests without launching the GUI:

```bash
pytest -q
```

## Notes

- This is a GUI app (`wxPython` + `PyVista` + `VTK`), so it is expected to run on a desktop session.
- Headless environments (for example, basic CI containers) usually need extra display setup and are not the primary target.
