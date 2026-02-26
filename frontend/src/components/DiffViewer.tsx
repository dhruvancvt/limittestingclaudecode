/**
 * Minimal unified-diff viewer.
 * Parses standard unified diff output (from Claude's file edits) and
 * renders it with green/red colouring.
 */
import { useMemo } from 'react'

interface DiffLine {
  type: 'header' | 'hunk' | 'add' | 'remove' | 'context' | 'meta'
  content: string
  lineNo?: { old?: number; new?: number }
}

function parseDiff(raw: string): DiffLine[] {
  const lines: DiffLine[] = []
  let oldLine = 1
  let newLine = 1

  for (const line of raw.split('\n')) {
    if (line.startsWith('diff ') || line.startsWith('index ')) {
      lines.push({ type: 'meta', content: line })
    } else if (line.startsWith('--- ') || line.startsWith('+++ ')) {
      lines.push({ type: 'header', content: line })
    } else if (line.startsWith('@@ ')) {
      const m = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)/)
      if (m) {
        oldLine = parseInt(m[1], 10)
        newLine = parseInt(m[2], 10)
      }
      lines.push({ type: 'hunk', content: line })
    } else if (line.startsWith('+')) {
      lines.push({ type: 'add', content: line.slice(1), lineNo: { new: newLine++ } })
    } else if (line.startsWith('-')) {
      lines.push({ type: 'remove', content: line.slice(1), lineNo: { old: oldLine++ } })
    } else {
      lines.push({
        type: 'context',
        content: line.startsWith(' ') ? line.slice(1) : line,
        lineNo: { old: oldLine++, new: newLine++ },
      })
    }
  }
  return lines
}

interface Props {
  diff: string
  onClose: () => void
}

export default function DiffViewer({ diff, onClose }: Props) {
  const parsed = useMemo(() => parseDiff(diff), [diff])

  return (
    <div className="diff-overlay" onClick={onClose}>
      <div className="diff-panel" onClick={(e) => e.stopPropagation()}>
        <div className="diff-toolbar">
          <span className="diff-title">File Changes</span>
          <button className="btn-icon" onClick={onClose} aria-label="Close diff">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="diff-body">
          <table className="diff-table">
            <tbody>
              {parsed.map((line, i) => {
                if (line.type === 'meta') return null
                if (line.type === 'header') {
                  return (
                    <tr key={i} className="diff-row-header">
                      <td className="diff-gutter" colSpan={2} />
                      <td className="diff-code">{line.content}</td>
                    </tr>
                  )
                }
                if (line.type === 'hunk') {
                  return (
                    <tr key={i} className="diff-row-hunk">
                      <td className="diff-gutter" colSpan={2} />
                      <td className="diff-code">{line.content}</td>
                    </tr>
                  )
                }
                return (
                  <tr key={i} className={`diff-row diff-row-${line.type}`}>
                    <td className="diff-gutter diff-gutter-old">
                      {line.type === 'remove' || line.type === 'context' ? line.lineNo?.old : ''}
                    </td>
                    <td className="diff-gutter diff-gutter-new">
                      {line.type === 'add' || line.type === 'context' ? line.lineNo?.new : ''}
                    </td>
                    <td className="diff-code">
                      <span className="diff-marker">
                        {line.type === 'add' ? '+' : line.type === 'remove' ? '-' : ' '}
                      </span>
                      {line.content}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
