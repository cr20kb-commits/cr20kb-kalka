# Microsoft Visual C++ Runtime

Приложению и его компонентам нужны библиотеки Microsoft Visual C++ Runtime. Шесть DLL из Redist включены в комплект, чтобы не требовать отдельной установки `vc_redist.exe`.

При сборке файлы извлекаются непосредственно из Microsoft Visual C++ Redistributable x64 14.51.36247, проверяются по SHA-256 и включаются без изменения в WebView2 Fixed Runtime. `vcruntime140.dll` и `vcruntime140_1.dll` также входят в каталог Python; `concrt140.dll`, `msvcp140.dll`, `msvcp140_codecvt_ids.dll` и `vccorlib140.dll` находятся в Fixed Runtime. Сборка отклоняет отсутствующий или несовпадающий CAB и неизвестные файлы семейства VC++ Runtime. Дата, версия, архитектура, хеши и путь к исходному CAB указаны в `MSVC_RUNTIME_BUILD_INFO.txt`; имена пользователей в пути нормализуются.

Распространение выполняется на основании Visual Studio Community 2022 License, Section 4, и документации Microsoft о Distributable Code и Visual C++ Runtime Files. Необходимые условия этих документов должны соблюдаться.

- [Visual Studio 2022 Distributable Code](https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution)
- [Redistributing Visual C++ Files](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files)
