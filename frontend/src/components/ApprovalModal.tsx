import type { PendingApproval } from '../types'

interface Props {
  approval: PendingApproval
  onApprove: () => void
  onReject: () => void
}

const TOOL_ICONS: Record<string, string> = {
  bash: '⚡',
  write_file: '✏️',
  read_file: '📄',
  str_replace_editor: '🔧',
  computer: '🖥️',
}

export default function ApprovalModal({ approval, onApprove, onReject }: Props) {
  const icon = TOOL_ICONS[approval.toolName.toLowerCase()] ?? '🔧'

  return (
    <div className="modal-backdrop" onClick={onReject}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="modal-header">
          <span className="modal-icon">{icon}</span>
          <div>
            <div className="modal-title">Tool Approval Required</div>
            <div className="modal-subtitle">
              Claude wants to use <strong>{approval.toolName}</strong>
            </div>
          </div>
        </div>

        {approval.toolInput && (
          <div className="modal-body">
            <div className="code-block">
              <div className="code-block-label">Command / Input</div>
              <pre className="code-block-content">
                <code>{approval.toolInput}</code>
              </pre>
            </div>
          </div>
        )}

        <div className="modal-actions">
          <button
            className="btn-reject"
            onClick={onReject}
            autoFocus={false}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
            Reject
          </button>
          <button
            className="btn-approve"
            onClick={onApprove}
            autoFocus
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            Approve
          </button>
        </div>

        <div className="modal-hint">
          Tap outside or press Reject to deny this action
        </div>
      </div>
    </div>
  )
}
