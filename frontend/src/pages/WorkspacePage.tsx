/**
 * WorkspacePage
 *
 * Route-level page for the main authenticated workspace experience.
 * Delegates layout to MainLayout, which owns:
 * - HeaderBar (global top bar)
 * - SidebarEnhanced (left sidebar)
 * - WorkspaceShell (center tabs + Browser)
 * - FooterBar (global footer)
 */

import MainLayout from '@/components/main/MainLayout';

export default function WorkspacePage() {
  return <MainLayout />;
}
