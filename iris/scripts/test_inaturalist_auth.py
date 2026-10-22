#!/usr/bin/env python3
"""
Script de validação manual de credenciais e autenticação na API do iNaturalist.
Verifica o arquivo secrets/inaturalist.json e testa a obtenção do token JWT.
"""

import sys
import os
import json
from pathlib import Path

# Garante suporte completo a UTF-8 no console do Windows
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
        if sys.stdin and hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Adiciona o diretório iris ao sys.path
iris_dir = Path(__file__).resolve().parent.parent
if str(iris_dir) not in sys.path:
    sys.path.insert(0, str(iris_dir))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.modules.bird_id.inaturalist_client import INaturalistClient, INaturalistAuthError

console = Console()

def main():
    console.print(Panel.fit("[bold cyan]IRIS - Validador de Credenciais iNaturalist[/bold cyan]", border_style="cyan"))

    # Procurar arquivo de credenciais
    candidates = [
        iris_dir / "secrets" / "inaturalist.json",
        iris_dir.parent / "secrets" / "inaturalist.json",
        Path.cwd() / "secrets" / "inaturalist.json",
        Path.cwd() / "iris" / "secrets" / "inaturalist.json",
    ]

    found_path = None
    for p in candidates:
        if p.exists():
            found_path = p
            break

    if not found_path:
        console.print("[bold red]❌ Arquivo de credenciais não encontrado![/bold red]\n")
        console.print("Locais verificados:")
        for p in candidates:
            console.print(f"  [dim]- {p}[/dim]")
        console.print("\n[yellow]Crie o arquivo [bold]secrets/inaturalist.json[/bold] contendo username e password.[/yellow]")
        return 1

    console.print(f"[green]✔ Arquivo de credenciais encontrado:[/green] [bold]{found_path}[/bold]")

    # Inspeciona credenciais configuradas
    try:
        with open(found_path, "r", encoding="utf-8") as f:
            creds_data = json.load(f)
    except Exception as e:
        creds_data = {}

    username = creds_data.get("username")
    password = creds_data.get("password")
    app_id = creds_data.get("app_id")
    app_secret = creds_data.get("app_secret")
    has_jwt = bool(creds_data.get("jwt_token"))

    if username and password and app_id and app_secret:
        auth_mode = "OAuth 2.0 (App ID + Secret + Login)"
    elif username and password:
        auth_mode = "Sessão Web Automática (Usuário + Senha - Sem OAuth App)"
    elif has_jwt:
        auth_mode = "Token JWT Manual"
    else:
        auth_mode = "Não identificado"

    client = INaturalistClient(credentials_path=found_path)

    console.print(f"\n[cyan]Modo de autenticação detectado:[/cyan] [bold yellow]{auth_mode}[/bold yellow]")
    console.print("[cyan]Autenticando e requisitando token JWT na API do iNaturalist...[/cyan]")
    try:
        jwt_token = client.get_valid_jwt(force_refresh=True)
        masked_jwt = jwt_token[:15] + "..." + jwt_token[-10:] if len(jwt_token) > 30 else "***"
        
        table = Table(title="Status da Autenticação", border_style="green")
        table.add_column("Item", style="bold")
        table.add_column("Valor / Status", style="green")
        table.add_row("Arquivo de Credenciais", str(found_path))
        table.add_row("Modalidade", auth_mode)
        table.add_row("Status", "AUTENTICADO COM SUCESSO ✔")
        table.add_row("Token JWT Obtido", masked_jwt)
        table.add_row("Expiração Estimada", f"{client._jwt_expires_at.strftime('%d/%m/%Y %H:%M:%S') if client._jwt_expires_at else 'N/A'}")
        
        console.print(table)
        console.print("\n[bold green]🎉 Conexão com iNaturalist validada e pronta para o módulo de identificação de aves![/bold green]")
        return 0

    except INaturalistAuthError as e:
        console.print(f"\n[bold red]❌ Falha de Autenticação:[/bold red] {e}")
        console.print("\n[yellow]Dicas de Resolução:[/yellow]")
        console.print("1. Se configurou usuário e senha, confirme se eles são os mesmos usados no login em inaturalist.org.")
        console.print("2. Se a conta foi criada via Google/Apple, crie uma senha direta em inaturalist.org/users/edit.")
        console.print("3. Se usou token JWT manual (jwt_token), verifique se ele não expirou (válido por 24h).")
        return 1
    except Exception as e:
        console.print(f"\n[bold red]❌ Erro inesperado:[/bold red] {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
