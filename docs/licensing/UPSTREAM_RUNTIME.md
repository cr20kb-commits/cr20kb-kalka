# Windows runtime components — upstream distribution candidate

The Python runtime files, including any Microsoft runtime DLLs, are retained
from the pinned official CPython 3.12.10 Windows embeddable ZIP. The Python
binary licence contains additional Microsoft Distributable Code conditions;
see `third_party_licenses/python/LICENSE.txt`.

The WebView2 Fixed Runtime files are retained from the pinned official
Microsoft Fixed Runtime CAB, without replacing individual DLLs. Microsoft
Edge WebView2 Runtime (Fixed Version) licence terms are in
`third_party_licenses/webview2-fixed/Microsoft-WebView2-Fixed-terms-en.txt`.
The SDK files are from the pinned official Microsoft WebView2 SDK package.

The assembly does not copy DLLs from the host system or separately extract
DLLs from a VC++ Redistributable package. Distribution remains conditional
on compliance with the applicable terms, including terms for distributors
and end users. This document does not establish that all obligations have
been satisfied for a particular distributor.
