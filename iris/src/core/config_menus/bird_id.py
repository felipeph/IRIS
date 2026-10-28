import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from src.core.config import config
from src.core.geo import GeoService
from .geolocation import _menu_geolocation


def _menu_bird_id(console: Console):
    """Sub-menu: Identificação de Aves (YOLO + iNaturalist / BioCLIP)."""
    while True:
        console.clear()
        console.print(Panel("[bold yellow]Configurações: Identificação de Aves (YOLO + iNaturalist / BioCLIP)[/bold yellow]", expand=False))
        
        table = Table(title="Identificação Taxonômica de Aves")
        table.add_column("Opção", style="cyan", justify="center")
        table.add_column("Configuração", style="bold white")
        table.add_column("Chave YAML", style="magenta")
        table.add_column("Valor Atual", style="green")
        
        enabled_val = config.get("modules.bird_id.enabled", True)
        table.add_row("1", "Ativar Módulo de Aves", "modules.bird_id.enabled", "[green]Sim[/green]" if enabled_val else "[red]Não[/red]")
        
        provider = config.get("modules.bird_id.classifier_type", "inaturalist")
        table.add_row("2", "Provedor Taxonômico (IA)", "modules.bird_id.classifier_type", f"[bold cyan]{provider}[/bold cyan]")
        
        min_conf = config.get("modules.bird_id.min_species_confidence", 0.70)
        table.add_row("3", "Limiar de Confiança para Ações", "modules.bird_id.min_species_confidence", f"{float(min_conf)*100:.0f}%")
        
        rename_val = config.get("modules.bird_id.rename_files", True)
        table.add_row("4", "Renomeação Segura (_Nome-PT_Nome-Cientifico)", "modules.bird_id.rename_files", "[green]Sim[/green]" if rename_val else "[red]Não[/red]")
        
        subfolder_val = config.get("modules.bird_id.organize_in_subfolders", True)
        table.add_row("5", "Organizar em Subpasta por Nome Popular", "modules.bird_id.organize_in_subfolders", "[green]Sim[/green]" if subfolder_val else "[red]Não[/red]")
        
        exif_val = config.get("modules.bird_id.write_exif_tags", True)
        table.add_row("6", "Injetar Metadados EXIF/IPTC (ExifTool)", "modules.bird_id.write_exif_tags", "[green]Sim[/green]" if exif_val else "[red]Não[/red]")
        
        tf_val = config.get("modules.bird_id.video_target_frames", 15)
        table.add_row("7", "Alvo de Frames Amostrados em Vídeo", "modules.bird_id.video_target_frames", str(tf_val))
        
        max_crops = config.get("modules.bird_id.video_max_crops", 5)
        table.add_row("8", "Recortes Extraídos por Vídeo", "modules.bird_id.video_max_crops", str(max_crops))
        
        crops_val = config.get("modules.bird_id.video_min_confident_crops", 2)
        table.add_row("9", "Mínimo de Recortes para Validar Vídeo", "modules.bird_id.video_min_confident_crops", str(crops_val))
        
        def_loc = GeoService.get_default_location()
        def_lat = def_loc.lat if def_loc else config.get("modules.bird_id.inaturalist.default_lat", -19.92)
        table.add_row("10", "Latitude Padrão (Prior Geo)", "modules.bird_id.inaturalist.default_lat", f"{float(def_lat):.4f}")
        
        def_lng = def_loc.lng if def_loc else config.get("modules.bird_id.inaturalist.default_lng", -43.94)
        table.add_row("11", "Longitude Padrão (Prior Geo)", "modules.bird_id.inaturalist.default_lng", f"{float(def_lng):.4f}")
        
        geo_acc = config.get("modules.bird_id.inaturalist.positional_accuracy_meters", 25000)
        table.add_row("12", "Raio de Confiança Geo (metros)", "modules.bird_id.inaturalist.positional_accuracy_meters", f"{int(geo_acc):,}m")
        
        zoom_val = config.get("modules.bird_id.zoom_threshold_mm", 300.0)
        table.add_row("13", "Limiar de Zoom Teleobjetiva (mm)", "modules.bird_id.zoom_threshold_mm", f"{float(zoom_val):.0f}mm")
        
        crops_folder = config.get("modules.bird_id.iris_crops_folder", "10_Aves/Recortes")
        table.add_row("14", "Pasta de Recortes no IRIS", "modules.bird_id.iris_crops_folder", f"[cyan]{crops_folder}[/cyan]")
        
        yolo_mod = config.get("modules.bird_id.yolo_model", "yolov8s.pt")
        table.add_row("15", "Modelo Detector YOLOv8", "modules.bird_id.yolo_model", str(yolo_mod))
        
        yolo_c = config.get("modules.bird_id.yolo_confidence", 0.25)
        table.add_row("16", "Confiança Mínima YOLO", "modules.bird_id.yolo_confidence", f"{float(yolo_c)*100:.0f}%")
        
        creds_p = config.get("modules.bird_id.inaturalist.credentials_file", "secrets/inaturalist.json")
        table.add_row("17", "Arquivo de Credenciais iNaturalist", "modules.bird_id.inaturalist.credentials_file", str(creds_p))
        
        burst_consensus_val = config.get("modules.bird_id.enable_burst_consensus", True)
        table.add_row("18", "Consenso de Espécies em Rajadas", "modules.bird_id.enable_burst_consensus", "[green]Sim[/green]" if burst_consensus_val else "[red]Não[/red]")
        
        min_agree = config.get("modules.bird_id.burst_min_agreement_ratio", 0.50)
        table.add_row("19", "Concordância Mínima na Rajada", "modules.bird_id.burst_min_agreement_ratio", f"{float(min_agree)*100:.0f}%")
        
        ee_val = config.get("modules.bird_id.enable_burst_early_exit", True)
        table.add_row("20", "Parada Antecipada em Rajadas (Early Exit)", "modules.bird_id.enable_burst_early_exit", "[green]Sim[/green]" if ee_val else "[red]Não[/red]")
        
        ee_confirms = config.get("modules.bird_id.burst_early_exit_confirmations", 3)
        table.add_row("21", "Confirmações Mínimas p/ Early Exit", "modules.bird_id.burst_early_exit_confirmations", f"{int(ee_confirms)} fotos")
        table.add_row("22", "Central de Geolocalizações (Locais Salvos)", "geo.locations", "[yellow]Gerenciar / Cadastrar[/yellow]")
        
        console.print(table)
        console.print("\n[cyan][0][/cyan] Voltar ao Menu de Categorias")
        
        choice = Prompt.ask("\nEscolha uma opção para editar", default="0")
        if choice == "0":
            break
        elif choice == "1":
            curr = config.get("modules.bird_id.enabled", True)
            new_val = Confirm.ask("Habilitar módulo de identificação de aves no pipeline?", default=curr)
            config.set("modules.bird_id.enabled", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "2":
            curr = config.get("modules.bird_id.classifier_type", "inaturalist")
            new_val = Prompt.ask("Provedor Taxonômico (inaturalist ou bioclip)", default=str(curr)).lower().strip()
            if new_val in ["inaturalist", "bioclip"]:
                config.set("modules.bird_id.classifier_type", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Provedor deve ser 'inaturalist' ou 'bioclip'![/red]")
            time.sleep(1)
        elif choice == "3":
            curr = float(config.get("modules.bird_id.min_species_confidence", 0.70))
            new_val = Prompt.ask("Limiar de confiança para ações ativas (0.10 a 0.99)", default=f"{curr:.2f}")
            try:
                val_f = float(new_val)
                if 0.10 <= val_f <= 0.99:
                    config.set("modules.bird_id.min_species_confidence", val_f)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve estar entre 0.10 e 0.99![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número decimal![/red]")
            time.sleep(1)
        elif choice == "4":
            curr = config.get("modules.bird_id.rename_files", True)
            new_val = Confirm.ask("Renomear arquivos incluindo _{Nome_PT}_{Cientifico}?", default=curr)
            config.set("modules.bird_id.rename_files", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "5":
            curr = config.get("modules.bird_id.organize_in_subfolders", True)
            new_val = Confirm.ask("Mover para subpasta com nome popular da espécie dentro da categoria?", default=curr)
            config.set("modules.bird_id.organize_in_subfolders", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "6":
            curr = config.get("modules.bird_id.write_exif_tags", True)
            new_val = Confirm.ask("Injetar tags taxonômicas nos metadados EXIF/IPTC via ExifTool?", default=curr)
            config.set("modules.bird_id.write_exif_tags", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "7":
            curr = config.get("modules.bird_id.video_target_frames", 15)
            new_val = Prompt.ask("Quantidade alvo de frames amostrados proporcionalmente à duração (5 a 60)", default=str(curr))
            try:
                tf_int = int(new_val)
                if 5 <= tf_int <= 60:
                    config.set("modules.bird_id.video_target_frames", tf_int)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve ser entre 5 e 60![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "8":
            curr = config.get("modules.bird_id.video_max_crops", 5)
            new_val = Prompt.ask("Quantidade de melhores recortes extraídos de cada vídeo (1 a 15)", default=str(curr))
            try:
                mc_crops = int(new_val)
                if 1 <= mc_crops <= 15:
                    config.set("modules.bird_id.video_max_crops", mc_crops)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve ser entre 1 e 15![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "9":
            curr = config.get("modules.bird_id.video_min_confident_crops", 2)
            new_val = Prompt.ask("Mínimo de recortes com a mesma espécie para consolidar o vídeo (1 a 10)", default=str(curr))
            try:
                mc_int = int(new_val)
                if 1 <= mc_int <= 10:
                    config.set("modules.bird_id.video_min_confident_crops", mc_int)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve ser entre 1 e 10![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "10":
            def_loc = GeoService.get_default_location()
            curr = def_loc.lat if def_loc else float(config.get("modules.bird_id.inaturalist.default_lat", -19.92))
            new_val = Prompt.ask("Latitude padrão para prior geográfico (-90.0 a 90.0)", default=f"{curr:.4f}")
            try:
                lat_f = float(new_val)
                if -90.0 <= lat_f <= 90.0:
                    config.set("modules.bird_id.inaturalist.default_lat", lat_f)
                    if def_loc:
                        def_loc.lat = lat_f
                        GeoService.update_location(def_loc)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Latitude deve estar entre -90.0 e 90.0![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número decimal![/red]")
            time.sleep(1)
        elif choice == "11":
            def_loc = GeoService.get_default_location()
            curr = def_loc.lng if def_loc else float(config.get("modules.bird_id.inaturalist.default_lng", -43.94))
            new_val = Prompt.ask("Longitude padrão para prior geográfico (-180.0 a 180.0)", default=f"{curr:.4f}")
            try:
                lng_f = float(new_val)
                if -180.0 <= lng_f <= 180.0:
                    config.set("modules.bird_id.inaturalist.default_lng", lng_f)
                    if def_loc:
                        def_loc.lng = lng_f
                        GeoService.update_location(def_loc)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Longitude deve estar entre -180.0 e 180.0![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número decimal![/red]")
            time.sleep(1)
        elif choice == "12":
            curr = int(config.get("modules.bird_id.inaturalist.positional_accuracy_meters", 25000))
            new_val = Prompt.ask("Raio de confiança/precisão geográfica em metros (ex: 25000 para 25km)", default=str(curr))
            try:
                acc_i = int(new_val)
                if 100 <= acc_i <= 500000:
                    config.set("modules.bird_id.inaturalist.positional_accuracy_meters", acc_i)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Raio deve estar entre 100m e 500.000m (500km)![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "13":
            curr = config.get("modules.bird_id.zoom_threshold_mm", 300.0)
            new_val = Prompt.ask("Distância focal equivalente mínima para elegibilidade (mm)", default=f"{float(curr):.0f}")
            try:
                val_f = float(new_val)
                if val_f >= 50.0:
                    config.set("modules.bird_id.zoom_threshold_mm", val_f)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve ser no mínimo 50mm![/red]")
            except ValueError:
                console.print("[red]Valor deve ser numérico![/red]")
            time.sleep(1)
        elif choice == "14":
            curr = config.get("modules.bird_id.iris_crops_folder", "10_Aves/Recortes")
            new_val = Prompt.ask("Subpasta na raiz de destino do IRIS para recortes (ex: 10_Aves/Recortes)", default=str(curr)).strip()
            if new_val:
                config.set("modules.bird_id.iris_crops_folder", new_val)
                console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "15":
            console.print("Modelos disponíveis: [bold]yolov8n.pt[/bold] (Nano/Rápido), [bold]yolov8s.pt[/bold] (Small/Padrão), [bold]yolov8m.pt[/bold] (Medium)")
            curr = config.get("modules.bird_id.yolo_model", "yolov8s.pt")
            new_val = Prompt.ask("Escolha o modelo YOLO", default=str(curr)).strip()
            if new_val in ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt"]:
                config.set("modules.bird_id.yolo_model", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Modelo inválido![/red]")
            time.sleep(1)
        elif choice == "16":
            curr = float(config.get("modules.bird_id.yolo_confidence", 0.25))
            new_val = Prompt.ask("Confiança mínima para detecção YOLO (0.10 a 0.90)", default=f"{curr:.2f}")
            try:
                val_f = float(new_val)
                if 0.10 <= val_f <= 0.90:
                    config.set("modules.bird_id.yolo_confidence", val_f)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve estar entre 0.10 e 0.90![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número decimal![/red]")
            time.sleep(1)
        elif choice == "17":
            curr = config.get("modules.bird_id.inaturalist.credentials_file", "secrets/inaturalist.json")
            new_val = Prompt.ask("Caminho do arquivo JSON com credenciais do iNaturalist", default=str(curr)).strip()
            if new_val:
                config.set("modules.bird_id.inaturalist.credentials_file", new_val)
                console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "18":
            curr = config.get("modules.bird_id.enable_burst_consensus", True)
            new_val = Confirm.ask("Habilitar consenso de espécies em fotos da mesma rajada (Soft Voting)?", default=curr)
            config.set("modules.bird_id.enable_burst_consensus", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "19":
            curr = float(config.get("modules.bird_id.burst_min_agreement_ratio", 0.50))
            new_val = Prompt.ask("Razão mínima de concordância entre fotos da rajada (0.20 a 1.00)", default=f"{curr:.2f}")
            try:
                val_f = float(new_val)
                if 0.20 <= val_f <= 1.00:
                    config.set("modules.bird_id.burst_min_agreement_ratio", val_f)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve estar entre 0.20 e 1.00![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número decimal![/red]")
            time.sleep(1)
        elif choice == "20":
            curr = config.get("modules.bird_id.enable_burst_early_exit", True)
            new_val = Confirm.ask("Habilitar parada antecipada (early exit) em rajadas após quorum de certeza?", default=curr)
            config.set("modules.bird_id.enable_burst_early_exit", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "21":
            curr = int(config.get("modules.bird_id.burst_early_exit_confirmations", 3))
            new_val = Prompt.ask("Número mínimo de confirmações com alta certeza para early exit (1 a 10 fotos)", default=str(curr))
            try:
                val_i = int(new_val)
                if 1 <= val_i <= 10:
                    config.set("modules.bird_id.burst_early_exit_confirmations", val_i)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve estar entre 1 e 10![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "22":
            _menu_geolocation(console)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)

