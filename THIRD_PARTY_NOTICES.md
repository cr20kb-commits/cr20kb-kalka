# Windows RC — сторонние компоненты

Документ описывает компоненты Windows 1.0.5. Условия сторонних компонентов и соответствующие уведомления включены в поставляемое приложение.

## Microsoft Visual C++ Runtime

Используется Microsoft Visual C++ Redistributable x64 **14.51.36247.0**. Шесть DLL извлечены без изменения из подтверждённого официального Microsoft Redist `vcRuntimeMinimum_amd64/cab1.cab`, SHA-256 CAB `6e8ee73933678c55973e83366e48e948b394c7a36743a36b7224c95de979b13f`. Исходный пакет: официальный Microsoft Visual C++ Redistributable / Visual Studio Redist; техническое описание — [Microsoft Redistribute Visual C++ files](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files). DLL не берутся из системных каталогов, архива CPython или пакета WebView2.

| DLL | SHA-256 |
| --- | --- |
| `concrt140.dll` | `54716f0738af891f283d213b5c8d11b25896bb8ee3097d301eae718560cf974e` |
| `msvcp140.dll` | `7c26614e1d733892c2deac7e245ce115504b1d80592dd0a01b08e3e5a55f89ca` |
| `msvcp140_codecvt_ids.dll` | `8a65c7596ef2e6938731f5a1058e7e40145b6d97967cc649231a076b9a608d78` |
| `vccorlib140.dll` | `09f93d5ff96ae09767f3e1af3cdd43a5a58f2598654fc63089429bb6f9f4737f` |
| `vcruntime140.dll` | `d1f4225df2cd877dbf130d5668a021dce3f94118455ff5ec952061c30afc9ce7` |
| `vcruntime140_1.dll` | `a7146c08f89fe5b04541ab507cdb59ff7b44534d4ba3c668a426c6450a03434e` |

Все шесть находятся в `FixedRuntime`; обе `vcruntime` дополнительно находятся в `app/runtime` для CPython. Все восемь копий побайтно совпали с файлами CAB; подписи шести DLL действительны. Данные об источнике также включены в приложение: `docs/licensing/MSVC_RUNTIME_BUILD_INFO.txt` и `docs/licensing/MSVC_RUNTIME.md`. Приложение использует системные интерфейсы Universal CRT Windows, не копируя их в комплект.

## Microsoft Edge WebView2

WebView2 SDK 1.0.3650.58 и официальный Microsoft WebView2 Fixed Runtime 156.0.4314.50 x64. Исходный CAB Microsoft SHA-256 `fcf0cd55f7c6e8efced05114372de8b8ffc9032c0296d16e060d260637dfe5f2`. Шесть DLL семейства VC++ в папке Fixed заменены неизменёнными файлами Redist; остальные 251 файл Fixed побайтно совпали с закреплённым манифестом.

Условия Fixed — `third_party_licenses/webview2-fixed/Microsoft-WebView2-Fixed-terms-en.txt`; SDK LICENSE и NOTICE — `third_party_licenses/webview2/`. В приложении предусмотрен доступ к Chromium credits. Действуют условия Microsoft для приложения, получателей и последующих распространителей. Fixed Runtime обновляется при обновлении комплекта приложения.

## Другие компоненты

- CPython 3.12.10 Windows embeddable — PSF и включённые условия, `third_party_licenses/python/LICENSE.txt`.
- Pillow 13.0.0 — MIT-CMU и уведомления включённых библиотек, `third_party_licenses/pillow/`. Программа частично основана на работе FreeType Team.
- pypdfium2 5.14.0 и PDFium 158.0.8111.0 — Apache-2.0/BSD-3-Clause и лицензии зависимостей, `third_party_licenses/pypdfium2/`. Bindings собраны локально. Предыдущий аудит сверил 22 лицензионных текста wheel и 19 уведомлений PDFium; статус сохранён CLEAR.
- OpenSSL и другие компоненты CPython/Pillow — лицензии внутри `third_party_licenses/`. Уведомление SmartScreen входит в комплект и диалог запуска.
- Лицензия `LICENSE` относится к частям, на которые CR20KB имеет необходимые права, и не заменяет условия сторонних компонентов.
