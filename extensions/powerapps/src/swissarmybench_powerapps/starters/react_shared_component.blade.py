# /// swissarmybench-blade
# format = 1
# name = "Shared component"
# kind = "snippet"
# description = "A component more than one page uses, for src/shared/components: typed props, no page's own state"
# tags = ["react", "tsx", "shared", "code app"]
# family = "React"
# language = "tsx"
# ///
snippet = r"""

import type { ReactNode } from "react";

interface Props {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
}

// Shared by pages (src/shared/components): it takes everything by props and keeps no page's state.
export function <<component name: Panel>>({ title, children, actions }: Props) {
  return (
    <section>
      <header>
        <h2>{title}</h2>
        {actions}
      </header>
      {children}
    </section>
  );
}
"""
