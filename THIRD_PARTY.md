# Third-party software

Shoestring Studios 2 (Copyright Sangho KIM (NexTopologix), PolyForm Noncommercial 1.0.0, see `LICENSE`) runs on Nextop Agentic Workers (nextop, a separate product, Copyright NexTopologix (Sangho KIM), PolyForm Small Business 1.0.0, installed from PyPI) and on the third-party software and services below, each under its own license or terms.

Shoestring Studios 2 stands on free software and a few services. Versions and licenses were read from the installed packages (this project's .venv, Kokoro's Python environment, remotion/node_modules) and from the code that calls each service; "not stated" means the package or file gives none.

## Framework

| Name | Version | License | What we use it for | Link |
| --- | --- | --- | --- | --- |
| Nextop Agentic Workers (nextop) | 0.1.2 | PolyForm Small Business 1.0.0 | The framework Shoestring 2 runs on: workers as blocks, the flow runner, file servers, the studio page (WORKERS ... ABOUT tabs), the OpenAI-compatible LLM adapter and the HTTP embedding adapter. A separate product, installed from PyPI (nextop>=0.1.2 in requirements.txt); not part of this repository. Copyright NexTopologix (Sangho KIM). | [nextop.nextopologix.com](https://nextop.nextopologix.com) &middot; [License](https://polyformproject.org/licenses/small-business/1.0.0) |

## Backend

| Name | Version | License | What we use it for | Link |
| --- | --- | --- | --- | --- |
| Python 3.11 Standard Library | 3.11.9 | PSF License | The site server (scripts/server.py), Sam, the run views and the tool/function HTTP calls run on the standard library (http.server, urllib, json). | [python.org](https://docs.python.org/3.11/license.html) |
| PyMuPDF (pymupdf) | 2.1 | AGPL-3.0 or Artifex commercial license (dual) | Order intake: draws PDF pages, finds figure regions and reads the text (scripts/pdf_to_package.py, scripts/server.py). Imported directly by our code. Copyleft: see the note below. | [PyPI](https://pypi.org/project/PyMuPDF/) |
| Pillow | 13.0.0 | MIT-CMU | Image checks, figure crops and the preview sheets (tools/fetch_image.py, generate_image.py, preview_materials.py, preview_slides.py, scripts/pdf_to_package.py). Imported directly by our code. | [PyPI](https://pypi.org/project/pillow/) |
| numpy | 2.4.6 | BSD-3-Clause (with 0BSD, MIT, Zlib, CC0-1.0 parts) | Embedding math in the LightRAG adapter (adapters/lightrag_index.py). Imported directly by our code. | [PyPI](https://pypi.org/project/numpy/) |

## AI & RAG

| Name | Version | License | What we use it for | Link |
| --- | --- | --- | --- | --- |
| qwen3.8-flash-next | — | not stated | All LLM work: every crew worker, Sam's order chat, the PDF intake vision step and LightRAG's entity extraction. Served by a local OpenAI-compatible server (project.json adapter "default", 127.0.0.1:8010). The model's license is not recorded in this repository. |  |
| LightRAG (lightrag-hku) | 1.5.7 | MIT | Knowledge-graph index of the SOURCE file server (file_servers/source, index "lightrag"; adapters/lightrag_index.py). Imported directly by our code. | [PyPI](https://pypi.org/project/lightrag-hku/) |
| networkx | 3.6.1 | BSD-3-Clause | Graph store behind LightRAG. | [PyPI](https://pypi.org/project/networkx/) |
| nano-vectordb | 0.0.4.3 | MIT | Vector store behind LightRAG. | [PyPI](https://pypi.org/project/nano-vectordb/) |
| tiktoken | 0.14.0 | MIT | Token counting behind LightRAG. | [PyPI](https://pypi.org/project/tiktoken/) |
| BAAI/bge-m3 | — | MIT | Embedding model for the LightRAG index (1024-dim vectors), served by our Jetson embedding server on the LAN (project.json embed adapter "jetson"; the server is not part of this repository). License read from its Hugging Face model card. | [Hugging Face](https://huggingface.co/BAAI/bge-m3) |

## Video

| Name | Version | License | What we use it for | Link |
| --- | --- | --- | --- | --- |
| Remotion (remotion, @remotion/cli, @remotion/renderer, @remotion/bundler) | 4.0.535 | Remotion License (proprietary; Free License) | Renders the slide stills (remotion/, tools/preview_materials.py, tools/preview_slides.py). Installed via npm, never bundled. Source-available, NOT open source: free for individuals and companies up to 3 employees, a Company License above that (remotion/node_modules/remotion/LICENSE.md). | [remotion.dev](https://www.remotion.dev/license) |
| @remotion/three | 4.0.535 | MIT | 3D scenes inside the slide templates (remotion/src/graphics.tsx). | [npm](https://www.npmjs.com/package/@remotion/three) |
| three (npm) + @react-three/fiber | 0.169.0 / 8.17.10 | MIT | 3D graphics behind @remotion/three in the slide templates. | [npm](https://www.npmjs.com/package/three) &middot; [npm](https://www.npmjs.com/package/@react-three/fiber) |
| React + react-dom | 18.3.1 | MIT | UI library of the Remotion slide templates. | [npm](https://www.npmjs.com/package/react) |
| KaTeX | 0.16.11 | MIT | Formula rendering in the slide templates. | [npm](https://www.npmjs.com/package/katex) |
| Pretendard (5 weights, remotion/public/fonts) | not stated | SIL Open Font License | Slide typeface. The license is from the Pretendard project page; no license file is stored next to the font files in this repository. | [GitHub](https://github.com/orioncactus/pretendard) |
| Kokoro | 0.9.4 | Apache-2.0 | Wren's narrator voice (tools/_kokoro_say.py). Installed into this project's .venv from requirements-voice.txt (KOKORO_PYTHON can point elsewhere). | [PyPI](https://pypi.org/project/kokoro/) |
| Kokoro-82M (voice model) | — | Apache-2.0 | Voice model weights Kokoro downloads on first use. License read from its Hugging Face model card. | [Hugging Face](https://huggingface.co/hexgrad/Kokoro-82M) |
| misaki | 0.9.4 | Apache-2.0 | Text-to-phoneme step behind Kokoro. | [PyPI](https://pypi.org/project/misaki/) |
| torch (CPU) | 2.15.0+cpu | BSD-3-Clause, Apache-2.0 and other permissive parts | Runs the Kokoro model (Kokoro's environment only). | [PyPI](https://pypi.org/project/torch/) |
| spaCy + en_core_web_sm | 3.8.18 / 3.8.0 | MIT | English text analysis behind misaki. | [PyPI](https://pypi.org/project/spacy/) |
| phonemizer-fork | 3.3.2 | GPL-3.0-or-later | Phonemizer behind misaki's fallback for unusual words. Installed by pip in Kokoro's environment, never bundled in this repository. | [PyPI](https://pypi.org/project/phonemizer-fork/) |
| espeakng-loader (with eSpeak NG) | 0.2.4 | loader: not stated; eSpeak NG: GPL-3.0-or-later | Ships the eSpeak NG library misaki uses for words it cannot spell. Installed by pip in Kokoro's environment, never bundled in this repository. | [PyPI](https://pypi.org/project/espeakng-loader/) &middot; [eSpeak NG](https://github.com/espeak-ng/espeak-ng) |
| soundfile | 0.14.0 | BSD-3-Clause | Writes Kokoro's audio to WAV (tools/_kokoro_say.py). | [PyPI](https://pypi.org/project/soundfile/) |
| FFmpeg (system install) | 9.0.2 (gyan.dev full build) | GPL-3.0-or-later (this build) | Joins slides and voice into the MP4, converts WAV to MP3, reads media lengths, takes gallery thumbnails (functions/assemble_video.py, functions/_common.py, scripts/site_runs.py). Found on PATH; not bundled. This build is configured with --enable-gpl --enable-version3. | [FFmpeg legal](https://ffmpeg.org/legal.html) |

## 3D & assets

| Name | Version | License | What we use it for | Link |
| --- | --- | --- | --- | --- |
| Three.js | 0.186.1 | MIT | 3D engine behind the Studio office (office_3d.html, office_editor.html). Vendored with its license in vendor/three/. © three.js authors. | [threejs.org](https://threejs.org) |
| Kenney Mini Characters 1.0 + Furniture Kit 2.0 | — | CC0 | Crew avatars and office furniture (vendor/kenney/). Public-domain dedication, no attribution required (credited here anyway). © Kenney (kenney.nl). | [Mini Characters](https://kenney.nl/assets/mini-characters) &middot; [Furniture Kit](https://kenney.nl/assets/furniture-kit) |

## Services

| Name | Version | License | What we use it for | Link |
| --- | --- | --- | --- | --- |
| Meta Model API — Muse Image 1.0 | — | Service (Meta terms) | Gene's generated pictures (muse-image-1.0, tools/generate_image.py). Needs MODEL_API_KEY. | [dev.meta.ai](https://dev.meta.ai/) |
| Tavily | — | Service (Tavily terms) | News search with article text for Cleo and Rex (tools/news_search.py; when the text is short, the article page itself is read). Needs TAVILY_API_KEY. | [tavily.com](https://tavily.com/) |
| Serper.dev (Google Images results) | — | Service (Serper terms); pictures: per website, not checked | Pia's photo search (tools/google_image_search.py); fetch_image.py downloads the chosen pictures. Falls back to the Google Custom Search JSON API (GOOGLE_API_KEY + GOOGLE_CSE_ID) when no SERPER_API_KEY is set. The code keeps each picture's source address but does not check its license. | [serper.dev](https://serper.dev/) &middot; [Custom Search](https://developers.google.com/custom-search/v1/overview) |
| Jetson embedding server (our own) | — | Our server (not in this repository) | Serves BAAI/bge-m3 embeddings on the LAN for the LightRAG index (project.json embed adapter "jetson", key EMBED_TOKEN). |  |

**Copyleft: PyMuPDF is AGPL-3.0 (or a paid Artifex license) and is imported by our intake code; phonemizer-fork and eSpeak NG are GPL-3.0-or-later and the FFmpeg build used here is GPL. None of them is copied into this repository; they are installed separately.**

*Verification only (not shipped): headless Edge drives the automated browser checks.*
