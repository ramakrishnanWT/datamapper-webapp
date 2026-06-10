#!/usr/bin/env bash
# Regenerate kaoto.patch against the current Kaoto main branch.
# Run from inside WSL: bash /mnt/c/.../scripts/_regen_patch.sh
set -euo pipefail

KAOTO_DIR=/tmp/kaoto-regen
PATCH_OUT=/mnt/c/Users/Rama.Ramasubramanian/PROJECTS/DX-DEMOPOC/datamapper-webapp/scripts/kaoto.patch

echo "==> Cloning Kaoto main..."
rm -rf "$KAOTO_DIR"
git clone --depth 1 --branch main https://github.com/KaotoIO/kaoto "$KAOTO_DIR"
cd "$KAOTO_DIR"

# ── index.html ────────────────────────────────────────────────────────────────
sed -i 's|<title>Kaoto</title>|<title>Data eXchange Mapper</title>|' \
    packages/ui/index.html

# ── MainMenuToolbarItem.tsx ───────────────────────────────────────────────────
sed -i 's/DataMapper Debugger/DataMapper - UI/' \
    packages/ui/src/components/DataMapper/debug/MainMenuToolbarItem.tsx

# ── ToggleDebugToolbarItem.tsx ────────────────────────────────────────────────
sed -i "s|import { BugIcon } from '@patternfly/react-icons';|import { CogIcon } from '@patternfly/react-icons';|" \
    packages/ui/src/components/DataMapper/debug/ToggleDebugToolbarItem.tsx
sed -i 's|icon={<BugIcon />}|icon={<CogIcon />}|' \
    packages/ui/src/components/DataMapper/debug/ToggleDebugToolbarItem.tsx
sed -i 's|aria-label="Enable debug mode"|aria-label="Actions"\n          title="Actions"|' \
    packages/ui/src/components/DataMapper/debug/ToggleDebugToolbarItem.tsx

# ── Shell.tsx — rewrite with DATAMAPPER_ONLY logic ───────────────────────────
cat > packages/ui/src/layout/Shell.tsx << 'TSX'
import './Shell.scss';

import { Page, PageSection } from '@patternfly/react-core';
import { FunctionComponent, PropsWithChildren, useCallback, useMemo } from 'react';

import { useLocalStorage } from '../hooks/local-storage.hook';
import { LocalStorageKeys } from '../models';
import { Navigation } from './Navigation';
import { TopBar } from './TopBar';

const DATAMAPPER_ONLY = import.meta.env.VITE_DATAMAPPER_ONLY === 'true';

export const Shell: FunctionComponent<PropsWithChildren> = (props) => {
  const defaultNavState = useMemo(() => {
    if (globalThis.innerWidth !== undefined) {
      return globalThis.innerWidth >= 1200;
    }
    // Server Side Rendering fallback can't be tested in JSDom
    return true;
  }, []);

  const [isNavOpen, setIsNavOpen] = useLocalStorage(LocalStorageKeys.NavigationExpanded, defaultNavState);

  const navToggle = useCallback(() => {
    setIsNavOpen(!isNavOpen);
  }, [isNavOpen, setIsNavOpen]);

  if (DATAMAPPER_ONLY) {
    return (
      <Page isContentFilled masthead={<TopBar navToggle={navToggle} hideNavToggle />}>
        <PageSection isFilled hasBodyWrapper={false} className="shell__page-section">
          {props.children}
        </PageSection>
      </Page>
    );
  }

  return (
    <Page isContentFilled masthead={<TopBar navToggle={navToggle} />} sidebar={<Navigation isNavOpen={isNavOpen} />}>
      <PageSection isFilled hasBodyWrapper={false} className="shell__page-section">
        {props.children}
      </PageSection>
    </Page>
  );
};
TSX

# ── TopBar.tsx — remove logo import, add hideNavToggle ───────────────────────
python3 - << 'PY'
import re, pathlib

p = pathlib.Path('packages/ui/src/layout/TopBar.tsx')
src = p.read_text()

# Remove logo import line
src = re.sub(r"import logo from '../assets/logo-kaoto\.png';\n", '', src)

# Add hideNavToggle to interface
src = src.replace(
    'interface ITopBar {\n  navToggle: () => void;\n}',
    'interface ITopBar {\n  navToggle: () => void;\n  hideNavToggle?: boolean;\n}'
)

# Wrap MastheadToggle in conditional
src = src.replace(
    '          <MastheadToggle>\n'
    '            <Button icon={<BarsIcon />} variant="plain" onClick={props.navToggle} aria-label="Global navigation" />\n'
    '          </MastheadToggle>\n',
    '          {!props.hideNavToggle && (\n'
    '            <MastheadToggle>\n'
    '              <Button icon={<BarsIcon />} variant="plain" onClick={props.navToggle} aria-label="Global navigation" />\n'
    '            </MastheadToggle>\n'
    '          )}\n'
)

# Replace logo img with DXM text
src = src.replace(
    '              <img className="shell__logo" src={logo} alt="Kaoto Logo" />',
    '              <span className="shell__logo-text" style={{ fontWeight: 600, fontSize: \'1.1rem\', color: \'var(--pf-v6-global--Color--100, #151515)\' }}>\n'
    '                Data eXchange Mapper\n'
    '              </span>'
)

p.write_text(src)
print("TopBar.tsx patched OK")
PY

# ── router.tsx — add DATAMAPPER_ONLY + dataMapperDebuggerLazy ─────────────────
python3 - << 'PY'
import pathlib

p = pathlib.Path('packages/ui/src/router.tsx')
src = p.read_text()

# Add DATAMAPPER_ONLY constant + lazy helper after the imports block
injection = """
const DATAMAPPER_ONLY = import.meta.env.VITE_DATAMAPPER_ONLY === 'true';

const dataMapperDebuggerLazy = async () => {
  if (import.meta.env.VITE_ENABLE_DATAMAPPER_DEBUGGER === 'true' || DATAMAPPER_ONLY) {
    return import('./components/DataMapper/debug/page');
  } else {
    return import('./pages/DataMapperNotYetInBrowser');
  }
};

"""
src = src.replace(
    "export const router = createHashRouter([",
    injection + "export const router = createHashRouter(["
)

# Change index route when DATAMAPPER_ONLY
src = src.replace(
    "        lazy: async () => import('./pages/Design'),",
    "        lazy: DATAMAPPER_ONLY ? dataMapperDebuggerLazy : async () => import('./pages/Design'),",
    1  # only first occurrence (the index route)
)

# Replace DataMapper route lazy with shared helper
old_dm = (
    "        lazy: async () => {\n"
    "          if (import.meta.env.VITE_ENABLE_DATAMAPPER_DEBUGGER === 'true') {\n"
    "            return import('./components/DataMapper/debug/page');\n"
    "          } else {\n"
    "            return import('./pages/DataMapperNotYetInBrowser');\n"
    "          }\n"
    "        },"
)
src = src.replace(old_dm, "        lazy: dataMapperDebuggerLazy,")

p.write_text(src)
print("router.tsx patched OK")
PY

echo "==> Generating patch..."
git diff > "$PATCH_OUT"
echo "==> Patch written to $PATCH_OUT"
wc -l "$PATCH_OUT"
