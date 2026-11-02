# CR20KB «Калька»

**Версия 1.0.5 для Windows x64** · [Скачать Setup](https://github.com/cr20kb-commits/cr20kb-kalka/releases/download/v1.0.5/CR20KB-Kalka-Setup.exe) · [Скачать Portable](https://github.com/cr20kb-commits/cr20kb-kalka/releases/download/v1.0.5/CR20KB-Kalka-Portable.zip) · [Страница CR20KB](https://cr20kb.com/utilities/kalka/)

Калька — инструмент визуального сравнения редакций технических чертежей и других графических документов путём наложения изображений или страниц PDF. Приложение поддерживает PDF, JPG и PNG, несколько слоёв, прозрачность и цветовое выделение, масштабирование и перемещение, подписи, даты и комментарии, сохранение проекта и экспорт PNG. Интерфейс доступен на русском, английском и китайском. Документы обрабатываются локально.

Результат зависит от совмещения исходных документов и не заменяет инженерную проверку.

## Windows: Setup

1. Скачайте `CR20KB-Kalka-Setup.exe` со [страницы релиза](https://github.com/cr20kb-commits/cr20kb-kalka/releases/tag/v1.0.5).
2. Запустите файл, прочитайте и примите условия компонентов.
3. Нажмите «Установить» и откройте Кальку через ярлык.

Setup рекомендуется большинству пользователей. Права администратора обычно не требуются; отдельная установка Python не нужна. Setup обновляет распознанные предыдущие версии и сохраняет пользовательские проекты и настройки. Прежняя папка программы сохраняется в резервной копии; если её принадлежность подтвердить не удалось, Setup запросит выбор. При удалении через «Установленные приложения» данные сохраняются.

## Windows: Portable

1. Скачайте `CR20KB-Kalka-Portable.zip` со [страницы релиза](https://github.com/cr20kb-commits/cr20kb-kalka/releases/tag/v1.0.5).
2. Полностью распакуйте архив в отдельную доступную для записи папку.
3. Запустите `KalkaPortable/Kalka.exe`.

Установка не требуется. Portable подходит для флешки и временного компьютера. Данные находятся в `KalkaData` рядом с программой; проекты удобно хранить отдельно.

## Проверка файла

Новые неподписанные приложения могут проходить дополнительную проверку Windows SmartScreen или сторонних антивирусов. Загружайте программу только с официальной страницы CR20KB или GitHub проекта и сверяйте SHA-256 с [SHA256SUMS.txt](https://github.com/cr20kb-commits/cr20kb-kalka/releases/download/v1.0.5/SHA256SUMS.txt).

```powershell
Get-FileHash .\CR20KB-Kalka-Setup.exe -Algorithm SHA256
```

Setup: `7a2081d35475492ede3e7e1f4e4086febaac136a3aaf3ff1e8ff18a7bd1cad13`  
Portable: `4617a66749b9549f154948742c2360030f66f1e8776c3ff5c5e1705d89f3c91c`

## Участники разработки

- **Сарвилин Владимир Владимирович** — автор идеи, идеолог и вдохновитель проекта.
- **ChatGPT (OpenAI)** — куратор разработки и архитектор постановки задач: формирование требований, декомпозиция, контроль решений и сопровождение разработки.
- **OpenAI Codex** — инженер-исполнитель: реализация, исправление, тестирование и сборка программного продукта.

Проект принадлежит CR20KB. Условия исходных частей — в [LICENSE](LICENSE), уведомления — в [NOTICE.md](NOTICE.md) и [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Сторонние компоненты, включая WebView2, Microsoft VC++ Runtime и PDFium, сохраняют собственные условия.

## English

CR20KB Kalka compares revisions of technical drawings and other graphical documents by overlaying PDF pages or JPG/PNG images. It supports layers, opacity and color, scaling and movement, labels, dates, project saving and PNG export. The interface is available in Russian, English and Chinese. Documents are processed locally. Check alignment manually; the comparison does not replace engineering review.

**Setup:** download `CR20KB-Kalka-Setup.exe`, run it, accept the component terms, select Install, and open Kalka from its shortcut. Administrator rights are usually unnecessary. Recognized earlier installations can be updated while preserving user projects and settings.

**Portable:** download `CR20KB-Kalka-Portable.zip`, extract it into a separate writable folder, and run `KalkaPortable/Kalka.exe`. No installation is required; it is suitable for a USB drive or temporary computer.

Unsigned applications may receive additional SmartScreen or antivirus checks. Download from the official CR20KB page or project GitHub and compare the SHA-256 values above.

### Development contributors

- **Vladimir Sarvilin** — project creator, ideologist and driving force behind the project.
- **ChatGPT (OpenAI)** — development curator and task architecture lead: requirements, decomposition, solution review and development guidance.
- **OpenAI Codex** — implementation engineer: development, debugging, testing and release assembly.

The project belongs to CR20KB. See [LICENSE](LICENSE), [NOTICE.md](NOTICE.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Source and build inputs

The Python, web-interface and native installer sources are included. The Windows binaries also contain separately licensed components and require their pinned build inputs; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the build scripts. `web/app.js` is transformed by `tools/save_bridge.py` for the Windows package. Binary artifacts are distributed through GitHub Releases, not stored in the source tree. Linux and standalone Web releases are outside this Windows release.
