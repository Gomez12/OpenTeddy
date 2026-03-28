# Skills Manager

Python script voor het zoeken, inspecteren en installeren van AI agent skills via [skills.sh](https://skills.sh).

## Vereisten

- Python 3.11+
- `git` (voor het klonen van repositories)
- Internettoegang (voor de skills.sh API en GitHub)

## Commando's

### search

Zoek naar skills op skills.sh.

```bash
python skills_manager.py search <query> [--limit N]
```

| Argument  | Beschrijving                     |
|-----------|----------------------------------|
| `query`   | Zoekterm                         |
| `--limit` | Maximaal aantal resultaten (standaard 10) |

Voorbeeld:

```bash
python skills_manager.py search "python testing"
```

Output:

```
Found 10 skill(s) for 'python testing':

  1. python-testing-patterns
     Source:   wshobson/agents
     Installs: 10475
     Install:  python skills_manager.py install wshobson/agents <directory> -s python-testing-patterns
```

### info

Bekijk welke skills er in een GitHub-repository zitten.

```bash
python skills_manager.py info <owner/repo> [-v]
```

| Argument        | Beschrijving                          |
|-----------------|---------------------------------------|
| `owner/repo`    | GitHub-repository (bijv. `jlowin/fastmcp`) |
| `-v, --verbose` | Toon de volledige SKILL.md inhoud     |

Voorbeeld:

```bash
python skills_manager.py info jlowin/fastmcp
python skills_manager.py info jlowin/fastmcp -v
```

Het commando kloont de repository tijdelijk, zoekt alle `SKILL.md` bestanden, en toont naam, beschrijving en pad van elke gevonden skill.

### install

Installeer skills vanuit een GitHub-repository naar een lokale directory.

```bash
python skills_manager.py install <owner/repo> [directory] [-s skill-name] [-f] [-g] [-u user]
```

| Argument        | Beschrijving                                              |
|-----------------|-----------------------------------------------------------|
| `owner/repo`    | GitHub-repository                                          |
| `directory`     | Doelmap waar de skills naartoe gekopieerd worden (optioneel als `-g` of `-u` wordt gebruikt) |
| `-s, --skill`   | Installeer alleen deze specifieke skill (op naam)          |
| `-f, --force`   | Overschrijf bestaande skills                               |
| `-g, --general` | Installeer naar `agentic/general/skills/`                  |
| `-u, --user`    | Installeer naar `agentic/user/<USER>/skills/` (de user directory moet al bestaan) |

Voorbeelden:

```bash
# Installeer naar een eigen directory
python skills_manager.py install wshobson/agents ./mijn-skills

# Installeer een specifieke skill naar de general skills directory
python skills_manager.py install jlowin/fastmcp -g -s testing-python

# Installeer naar een user-specifieke directory
python skills_manager.py install jlowin/fastmcp -u jan -s testing-python

# Bestaande skills overschrijven
python skills_manager.py install jlowin/fastmcp -g -f
```

Elke skill wordt als aparte subdirectory gekopieerd naar de doelmap.

## Hoe het werkt

1. **search** -- Bevraagt de `skills.sh/api/search` API en toont de resultaten.
2. **info / install** -- Kloont de repository met `git clone --depth 1` naar een tijdelijke directory, zoekt recursief naar `SKILL.md` bestanden, parseert de YAML-frontmatter (`name` en `description` zijn verplicht), en toont of kopieert de gevonden skills.

## Bronformaten

Het `owner/repo` argument ondersteunt ook subpaden:

```bash
# Hele repository doorzoeken
python skills_manager.py info vercel-labs/agent-skills

# Alleen een specifiek pad binnen de repo
python skills_manager.py info vercel-labs/agent-skills/skills/subdir
```
