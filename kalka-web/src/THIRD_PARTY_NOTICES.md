# Сторонние компоненты Web 0.2.0 preview

- PDF.js `pdfjs-dist` 5.6.205, Apache-2.0: `vendor/pdfjs/LICENSE`.
- В составе поставляемых PDF.js ресурсов находятся CMaps, стандартные шрифты, ICC и декодеры WASM. Их отдельные уведомления и лицензии сохранены в `vendor/pdfjs/cmaps/LICENSE`, `vendor/pdfjs/standard_fonts/LICENSE_*`, `vendor/pdfjs/iccs/LICENSE` и `vendor/pdfjs/wasm/LICENSE_*`.
- Canvas, Web Worker, Service Worker и IndexedDB предоставляются браузером и не входят как сторонние библиотеки в пакет.

Условия собственного кода — `LICENSE`. Сведения относятся именно к веб-пакету, а не к компонентам Windows-сборки. Исходный `pdfjs-dist` получен из локально установленного пакета; его лицензии и runtime-ресурсы включены без изменений.
