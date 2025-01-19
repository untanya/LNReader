import os
import re
import fitz
import base64
from dataclasses import dataclass
from typing import List, Dict, Optional
from langdetect import detect


@dataclass
class ChapterInfo:
    number: int
    title: str
    content: str


@dataclass
class NovelMetadata:
    title: str
    language: str
    author: Optional[str] = None
    series: Optional[str] = None
    volume: Optional[str] = None


class NovelPatternMatcher:
    """Gère les patterns de reconnaissance pour différents formats de novels."""

    def __init__(self):
        self.patterns = {
            "fr": {
                "chapter": [
                    r"(?i)^chapitre\s*(\d+)\s*[:|\-|–]?\s*(.*)$",
                    r"(?i)^partie\s*(\d+)\s*[:|\-|–]?\s*(.*)$",
                ],
                "dialogue": ["—", "–", "-"],
                "section": [
                    r"(?i)^(prologue)\s*[:|\-|–]?\s*(.*)$",
                    r"(?i)^(épilogue)\s*[:|\-|–]?\s*(.*)$",
                ],
            },
            "en": {
                "chapter": [
                    r"(?i)^chapter\s*(\d+)\s*[:|\-|–]?\s*(.*)$",
                    r"(?i)^part\s*(\d+)\s*[:|\-|–]?\s*(.*)$",
                ],
                "dialogue": ['"', "'", '"', '"'],
                "section": [
                    r"(?i)^(prologue)\s*[:|\-|–]?\s*(.*)$",
                    r"(?i)^(epilogue)\s*[:|\-|–]?\s*(.*)$",
                ],
            },
            "ja": {
                "chapter": [
                    r"^第(\d+)章\s*[:|\-|–]?\s*(.*)$",
                    r"^(\d+)章\s*[:|\-|–]?\s*(.*)$",
                ],
                "dialogue": ["「", "」"],
                "section": [
                    r"^(プロローグ)\s*[:|\-|–]?\s*(.*)$",
                    r"^(エピローグ)\s*[:|\-|–]?\s*(.*)$",
                ],
            },
        }

    def get_patterns(self, language: str) -> Dict:
        """Retourne les patterns pour une langue donnée."""
        return self.patterns.get(language, self.patterns["en"])

    def detect_chapter(self, text: str, language: str) -> Optional[tuple]:
        """Détecte si une ligne est un chapitre."""
        patterns = self.get_patterns(language)["chapter"]
        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                return match.groups()
        return None


class TextProcessor:
    def __init__(self, language: str):
        self.language = language
        self.pattern_matcher = NovelPatternMatcher()
        self.patterns = self.pattern_matcher.get_patterns(language)
        self.sentence_endings = {".", "!", "?", "...", "。", "！", "？"}

    def process_content(self, text: str) -> str:
        """Traite le contenu du texte en gérant dialogues et paragraphes."""
        lines = [line.strip() for line in text.split("\n") if self._is_valid_line(line)]
        paragraphs = []
        current_paragraph = ""
        in_dialogue = False

        for line in lines:
            # Vérifier si c'est un dialogue
            if self._is_dialogue_start(line):
                if current_paragraph and not in_dialogue:
                    paragraphs.append(self._wrap_paragraph(current_paragraph))
                    current_paragraph = ""
                in_dialogue = True
                current_paragraph += line + " "
            elif in_dialogue:
                current_paragraph += line + " "
                if self._is_sentence_end(line):
                    paragraphs.append(self._wrap_dialogue(current_paragraph))
                    current_paragraph = ""
                    in_dialogue = False
            else:
                current_paragraph += line + " "
                if self._is_sentence_end(line):
                    paragraphs.append(self._wrap_paragraph(current_paragraph))
                    current_paragraph = ""

        if current_paragraph:
            paragraphs.append(
                self._wrap_dialogue(current_paragraph)
                if in_dialogue
                else self._wrap_paragraph(current_paragraph)
            )

        return "\n".join(paragraphs)

    def _is_valid_line(self, line: str) -> bool:
        """Vérifie si une ligne doit être traitée."""
        if not line.strip():
            return False
        if line.startswith(("http://", "https://")):
            return False
        # Ajouter d'autres conditions si nécessaire
        return True

    def _is_dialogue_start(self, line: str) -> bool:
        """Vérifie si la ligne commence par un marqueur de dialogue."""
        return any(
            line.strip().startswith(marker) for marker in self.patterns["dialogue"]
        )

    def _is_sentence_end(self, line: str) -> bool:
        """Vérifie si la ligne se termine par une fin de phrase."""
        return any(line.strip().endswith(end) for end in self.sentence_endings)

    def _wrap_paragraph(self, text: str) -> str:
        """Enveloppe le texte dans des balises de paragraphe."""
        return f"<p>{text.strip()}</p>"

    def _wrap_dialogue(self, text: str) -> str:
        """Enveloppe le texte dans des balises de dialogue."""
        return f"<blockquote>{text.strip()}</blockquote>"


class NovelConverter:
    def __init__(self, metadata: NovelMetadata):
        self.metadata = metadata
        self.chapters: List[ChapterInfo] = []
        self.images: List[Dict] = []
        self.processor = TextProcessor(metadata.language)
        self.pattern_matcher = NovelPatternMatcher()

    def process_pdf(self, pdf_path: str) -> None:
        """Traite le PDF et extrait le contenu et les images."""
        doc = fitz.open(pdf_path)
        try:
            self._extract_content(doc)
            self._extract_images(doc)
        finally:
            doc.close()

    def _extract_content(self, doc) -> None:
        """Extrait et traite le contenu textuel du PDF."""
        current_chapter = []
        chapter_number = 0

        for page in doc:
            text = page.get_text()
            lines = text.split("\n")

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                chapter_match = self.pattern_matcher.detect_chapter(
                    line, self.metadata.language
                )

                if chapter_match:
                    # Sauvegarder le chapitre précédent s'il existe
                    if current_chapter:
                        self._save_chapter(chapter_number, current_chapter)

                    chapter_number = int(chapter_match[0])
                    current_chapter = [chapter_match[1] if chapter_match[1] else ""]
                else:
                    if (
                        current_chapter or not self.chapters
                    ):  # Si dans un chapitre ou premier texte
                        current_chapter.append(line)

        # Sauvegarder le dernier chapitre
        if current_chapter:
            self._save_chapter(chapter_number, current_chapter)

    def _save_chapter(self, number: int, content: List[str]) -> None:
        """Sauvegarde un chapitre traité."""
        title = content[0] if content else f"Chapter {number}"
        processed_content = self.processor.process_content("\n".join(content[1:]))
        self.chapters.append(ChapterInfo(number, title, processed_content))

    def _extract_images(self, doc) -> None:
        """Extrait les images du PDF."""
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()

            for img_idx, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]

                    img_data = base64.b64encode(image_bytes).decode("utf-8")
                    self.images.append(
                        {
                            "data": f"data:image/jpeg;base64,{img_data}",
                            "alt": f"Image {page_num+1}-{img_idx+1}",
                        }
                    )
                except Exception as e:
                    print(f"Erreur lors de l'extraction de l'image: {e}")

    def save_html(self, output_path: str) -> None:
        """Génère et sauve le fichier HTML final."""
        html_content = self._generate_html()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

    def _generate_html(self) -> str:
        """Génère le contenu HTML avec le style approprié."""
        # Le template HTML reste le même que dans votre code original
        # Vous pouvez le personnaliser selon vos besoins
        return self._get_html_template().format(
            title=self.metadata.title,
            language=self.metadata.language,
            toc=self._generate_toc(),
            content=self._generate_content(),
        )

    def _generate_toc(self) -> str:
        """Génère la table des matières."""
        return "\n".join(
            f'<li><a class="toc-item" href="#chapter-{chapter.number}">'
            f"{chapter.title}</a></li>"
            for chapter in self.chapters
        )

    def _generate_content(self) -> str:
        """Génère le contenu principal avec les chapitres et images."""
        content = []
        images_per_chapter = max(1, len(self.images) // max(1, len(self.chapters)))
        current_image = 0

        for chapter in self.chapters:
            # Ajouter le contenu du chapitre
            chapter_content = f"""
            <div class="chapter" id="chapter-{chapter.number}">
                <h2 class="chapter-title">{chapter.title}</h2>
                {chapter.content}
            </div>
            """
            content.append(chapter_content)

            # Ajouter les images assignées à ce chapitre
            for _ in range(images_per_chapter):
                if current_image < len(self.images):
                    content.append(
                        f'<div class="image-container">'
                        f'<img src="{self.images[current_image]["data"]}" '
                        f'alt="{self.images[current_image]["alt"]}">'
                        f"</div>"
                    )
                    current_image += 1

        # Ajouter les images restantes à la fin si nécessaire
        while current_image < len(self.images):
            content.append(
                f'<div class="image-container">'
                f'<img src="{self.images[current_image]["data"]}" '
                f'alt="{self.images[current_image]["alt"]}">'
                f"</div>"
            )
            current_image += 1

        return "\n".join(content)

    def _extract_images(self, doc) -> None:
        """Extrait les images du PDF en évitant les doublons."""
        seen_images = set()  # Pour stocker les hash des images

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()

            for img_idx, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]

                    # Vérifier la taille minimale
                    if len(image_bytes) < 10000:  # Ignorer les trop petites images
                        continue

                    # Créer un hash de l'image pour détecter les doublons
                    img_hash = hash(image_bytes)
                    if img_hash in seen_images:
                        continue

                    seen_images.add(img_hash)
                    img_data = base64.b64encode(image_bytes).decode("utf-8")
                    self.images.append(
                        {
                            "data": f"data:image/jpeg;base64,{img_data}",
                            "alt": f"Illustration {len(self.images) + 1}",
                        }
                    )

                except Exception as e:
                    print(f"Erreur lors de l'extraction de l'image: {e}")

    def _get_html_template(self) -> str:
        """Retourne le template HTML avec les styles."""
        return """<!DOCTYPE html>
            <html lang="{language}">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>{title}</title>
                <style>
                    :root {{
                        --bg-color: #1a1a1a;
                        --text-color: #e0e0e0;
                        --header-bg: #2d2d2d;
                        --link-color: #66b3ff;
                    }}
                    
                    body {{
                        background-color: var(--bg-color);
                        color: var(--text-color);
                        font-family: 'Arial', sans-serif;
                        line-height: 1.6;
                        margin: 0;
                        padding: 0;
                    }}
                    
                    .header {{
                        background-color: var(--header-bg);
                        padding: 1rem;
                        position: sticky;
                        top: 0;
                        z-index: 100;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
                    }}
                    
                    .container {{
                        max-width: 800px;
                        margin: 0 auto;
                        padding: 1rem;
                    }}
                    
                    .image-container {{
                        display: flex;  
                        justify-content: center;
                        align-items: center;
                        margin: 2rem 0;
                        width: 100%;
                    }}
                    
                    .chapter {{
                        margin-bottom: 2rem;
                        padding: 1rem;
                        background-color: rgba(255,255,255,0.05);
                        border-radius: 8px;
                    }}
                    
                    .chapter-title {{
                        color: var(--link-color);
                        margin-bottom: 1rem;
                    }}
                    
                    .toc {{
                        margin: 2rem 0;
                        padding: 1rem;
                        background-color: var(--header-bg);
                        border-radius: 8px;
                    }}
                    
                    .toc-item {{
                        color: var(--link-color);
                        text-decoration: none;
                    }}
                    
                    .toc-item:hover {{
                        text-decoration: underline;
                    }}
                    
                    img {{
                        max-width: 100%;
                        height: auto;
                        border-radius: 8px;
                        margin: 1rem 0;
                    }}
                    
                    p {{
                        margin-bottom: 1.5em;
                        text-align: justify;
                    }}
                    
                    blockquote {{
                        margin: 1.5rem 0;
                        padding: 1rem;
                        background-color: rgba(255, 255, 255, 0.1);
                        border-left: 4px solid var(--link-color);
                        font-style: italic;
                        color: var(--text-color);
                    }}
                    
                    @media (max-width: 768px) {{
                        .container {{
                            padding: 0.5rem;
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <div class="container">
                        <h1>{title}</h1>
                    </div>
                </div>
                
                <div class="container">
                    <div class="toc">
                        <h2>Table des matières</h2>
                        <ul>
                            {toc}
                        </ul>
                    </div>
                    
                    {content}
                </div>
            </body>
            </html>"""


def convert_novel(pdf_path: str, output_path: str, title: str = None) -> bool:
    """Fonction principale pour convertir un novel PDF en HTML."""
    try:
        # Détecter la langue du document
        doc = fitz.open(pdf_path)
        sample_text = ""
        for page in range(min(5, len(doc))):  # Échantillon des 5 premières pages
            sample_text += doc[page].get_text()
        doc.close()

        detected_language = detect(sample_text)[
            :2
        ]  # Prendre les 2 premiers caractères (fr, en, ja, etc.)

        # Créer les métadonnées
        metadata = NovelMetadata(
            title=title or os.path.splitext(os.path.basename(pdf_path))[0],
            language=detected_language,
        )

        # Initialiser et utiliser le convertisseur
        converter = NovelConverter(metadata)
        converter.process_pdf(pdf_path)
        converter.save_html(output_path)

        return True
    except Exception as e:
        print(f"Erreur lors de la conversion: {e}")
        return False


# Utilisation simple
success = convert_novel(
    "./input/Mushoku Tensei (LN) – Tome 15.pdf",
    "./output/Mushoku Tensei (LN) - Tome 15.html",
    "Mushoku Tensei",
)

# Ou avec plus de contrôle
metadata = NovelMetadata(
    title="Mushoku Tensei",
    language="fr",
    author="Rifujin na Magonote",
    volume="Tome 16",
)
converter = NovelConverter(metadata)
converter.process_pdf("./input/Mushoku Tensei (LN) – Tome 15.pdf")
converter.save_html("./output/Mushoku Tensei (LN) - Tome 15.html")
