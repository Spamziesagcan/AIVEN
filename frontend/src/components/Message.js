export default function Message({ message, index }) {
  const isUser = message.role === 'user'
  const timeLabel = formatTime(message.timestamp)
  const actorLabel = isUser ? 'You' : 'Ollive'

  return (
    <div
      className={`message ${isUser ? 'user' : 'assistant'}`}
      style={{ ['--delay']: `${Math.min(index * 40, 200)}ms` }}
    >
      <div className="message-avatar" aria-hidden="true">
        {isUser ? 'Y' : 'O'}
      </div>
      <div className="message-body">
        <div className="message-topline">
          <span className="message-actor">{actorLabel}</span>
          <span className="meta">{timeLabel}</span>
        </div>
        <div className="bubble" dangerouslySetInnerHTML={{ __html: format(message.content) }} />
      </div>
    </div>
  )
}

function formatTime(timestamp) {
  if (!timestamp) {
    return ''
  }

  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  })
    .format(new Date(timestamp))
    .toLowerCase()
}

function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function format(text = '') {
  return text
    .split(/\r?\n/)
    .map((line) => {
      if (!line.trim()) {
        return '<br/>'
      }

      const heading = line.match(/^(#{1,6})\s+(.+)$/)
      if (heading) {
        const level = Math.min(heading[1].length, 6)
        return `<h${level}>${formatInline(heading[2])}</h${level}>`
      }

      return `<p>${formatInline(line)}</p>`
    })
    .join('')
}

function formatInline(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
}
