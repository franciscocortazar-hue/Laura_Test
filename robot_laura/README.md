# Robot Laura — Sistema de Pruebas B4U

## Estructura
```
robot_laura/
├── CLAUDE_CODE.md       ← instrucciones para Claude Code
├── CLAUDE_COWORK.md     ← instrucciones para Cowork
├── runner.py            ← script principal
├── scenarios/
│   ├── CODE_T01-T09    ← 9 escenarios Make + Supabase
│   └── COWORK_T01,T02,T06,T10 ← 4 escenarios Laura
└── reports/
```

## Division de trabajo
| Herramienta | Escenarios | Que prueba |
|---|---|---|
| Claude Code | T01-T09 | Make + Supabase — motor backend |
| Cowork | T01,T02,T06,T10 | Laura — comportamiento conversacional |

## Ejecutar — Claude Code
```bash
export SUPABASE_SERVICE_ROLE_KEY="tu_key"
pip install requests
python runner.py
```

## Filosofia: Probar fuerte primero. Parchear despues.
