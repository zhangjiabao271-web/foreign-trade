# Third-party notices

## shadcn/ui Button

Source retrieved 2026-09-08:
https://ui.shadcn.com/r/styles/new-york-v4/button.json
License verified at https://raw.githubusercontent.com/shadcn-ui/ui/main/LICENSE.md
Local modifications: workbench CSS variants, native-only button, no size presets
or Slot, no redundant class-merging wrapper, default non-submit type, type imports.

MIT License

Copyright (c) 2023 shadcn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Packaged dependency

class-variance-authority 0.7.1: Apache-2.0 as declared in npm version metadata;
its clsx dependency uses MIT. These are package dependencies, not copied source.
Preserve their distributed license/notice files when shipping runtime artifacts.
The installed license texts were also inspected and retained in licenses/;
the Web Dockerfile carries this notice and both texts into /app/licenses/ui.
This is not a complete transitive-license or security audit.
