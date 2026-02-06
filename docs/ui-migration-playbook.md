# UI Migration Playbook

This plan is designed for parallel work with minimal merge conflicts.

## Current foundation (already added)
- Theme/appearance settings keys:
  - `ui.theme.mode`: `dark | light | system`
  - `ui.theme.accent`: `cyan | emerald | amber`
  - `ui.theme.density`: `compact | cozy`
- Tokenized base styles in `web/src/main.css`
- Shared primitives in `web/src/components/ui/*`
- Theme helpers in `web/src/theme/applyTheme.ts`

## Rules for parallel migration
- Prefer replacing raw utility strings with `ui/*` primitives.
- Keep behavior unchanged; migrate visuals first.
- Migrate one file at a time; avoid broad formatting-only changes.
- After each file: run `cd web && pnpm build`.

## Suggested migration order
1. Modals and pickers:
   - `web/src/components/SettingsModal.tsx`
   - `web/src/components/FolderPicker.tsx`
   - `web/src/components/SessionPicker.tsx`
2. Header/status controls:
   - `web/src/components/LayoutToggle.tsx`
   - `web/src/components/AgentStatusBar.tsx`
   - `web/src/components/PermissionBanner.tsx`
3. Messaging surfaces:
   - `web/src/components/ChatRoom.tsx`
   - `web/src/components/SharedChat.tsx`
   - `web/src/components/MessageBubble.tsx`
   - `web/src/components/StreamingBubble.tsx`
4. Task board:
   - `web/src/components/KanbanPanel.tsx`
   - `web/src/components/CardForm.tsx`
   - `web/src/components/CardItem.tsx`
5. Remaining utility views:
   - `web/src/components/AgentPanel.tsx`
   - `web/src/components/AgentPanels.tsx`
   - `web/src/components/PromptInput.tsx`
   - `web/src/components/RosterEditor.tsx`
   - `web/src/components/Toast.tsx`

## Primitive usage map
- Primary/secondary/ghost actions: `Button`
- Text/number/search fields: `Input`
- Multi-line fields: `Textarea`
- Drop-down fields: `Select`
- Boolean toggles: `Switch`
- Dialog shell: `Modal`
- Grouped controls/status: `Panel`
- Tab headers/content: `Tabs`, `TabPane`
- Compact status labels: `Badge`
- Horizontal form rows: `FieldRow`

## Post-migration checks
- `cd web && pnpm build`
- Manual sanity:
  - Session list and creation flow
  - Chat in split and unified layouts
  - Settings save/reset paths
  - Permission prompts and toasts
  - Mobile width behavior (375px)
