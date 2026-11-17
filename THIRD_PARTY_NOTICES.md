# Third-party notices

Keepsake includes or uses the following third-party works.

## qrcode-generator (bundled in dist/index.js)

QR Code Generator for JavaScript, https://github.com/kazuhikoarase/qrcode-generator

Copyright (c) 2009 Kazuhiko Arase

The word "QR Code" is a registered trademark of DENSO WAVE INCORPORATED.

Licensed under the MIT licence:

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## pysmb (vendored in py_modules/keepsake/_vendor)

pysmb 1.2.15, https://github.com/miketeo/pysmb, used to read Windows shares (ADR-0034). Altered: `smb/base.py` and `smb/SMBConnection.py` replace the `tqdm` import with a stub, marked "Keepsake patch (ADR-0034)"; `smb/SMBProtocol.py`, `nmb/NetBIOSProtocol.py` and `smb/SMBHandler.py` are left out.

Copyright (C) 2001-2025 Michael Teo

Licensed under the zlib/libpng licence:

> This software is provided 'as-is', without any express or implied warranty. In no event will the author be held liable for any damages arising from the use of this software.
>
> Permission is granted to anyone to use this software for any purpose, including commercial applications, and to alter it and redistribute it freely, subject to the following restrictions:
>
> 1. The origin of this software must not be misrepresented; you must not claim that you wrote the original software. If you use this software in a product, an acknowledgment in the product documentation would be appreciated but is not required.
> 2. Altered source versions must be plainly marked as such, and must not be misrepresented as being the original software.
> 3. This notice cannot be removed or altered from any source distribution.

## pyasn1 (vendored in py_modules/keepsake/_vendor)

pyasn1 0.6.5, https://github.com/pyasn1/pyasn1, used by pysmb.

Copyright (c) 2005-2020, Ilya Etingof. All rights reserved.

Licensed under the BSD 2-Clause licence:

> Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
>
> - Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
> - Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

## Ludusavi Manifest (downloaded at run time, not bundled)

Save location data comes from the Ludusavi Manifest, https://github.com/mtkennerly/ludusavi-manifest, compiled from PCGamingWiki.

Copyright (c) 2020 Matthew T. Kennerly (mtkennerly)

Licensed under the MIT licence, with the same terms as above.

## Are We Anti-Cheat Yet (downloaded at run time; status wording included in the Advisor)

Anti-cheat status comes from Are We Anti-Cheat Yet, https://github.com/AreWeAntiCheatYet/AreWeAntiCheatYet. The Advisor downloads its `games.json` at run time and uses the project's own wording for each status.

Copyright © 2021 Starz0r, Curve

Licensed under the MIT licence, with the same terms as above.

## Deck Verified (fetched at run time, not bundled)

Community reports come from Deck Verified by DeckSettings, https://deckverified.games. The report data is GPL-3.0. Keepsake shows it with a link to each report and caches it on the device only. No report data is part of Keepsake.
