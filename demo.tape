# VHS Demo Recording Script for NEXUS9
Output .github/assets/demo.gif
Set FontSize 14
Set Width 850
Set Height 520
Set Theme "Catppuccin Mocha"
Set Padding 20
Set WindowBar Colorful

Type "# Verificando status e integridade do runtime local NEXUS9"
Enter
Sleep 1s

Type "python integration.py verify"
Enter
Sleep 3s

Type "# Executando suite de testes de aceitacao (87 testes)"
Enter
Sleep 1s

Type "python -m unittest discover -s tests -v"
Enter
Sleep 4s

Type "# Inspecionando saude do motor de orcamentos e AST"
Enter
Sleep 1s

Type "python scripts/smoke.py"
Enter
Sleep 4s
