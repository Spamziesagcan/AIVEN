export default function Sidebar({
  conversations,
  activeConversationId,
  onNewConversation,
  onSelectConversation,
  onDeleteConversation,
}) {
  const previousConversations = conversations.filter((conversation) => conversation.id !== activeConversationId)

  return (
    <aside className="sidebar">
      <div className="sidebar-actions">
        <button type="button" className="new" onClick={onNewConversation}>
          New conversation
        </button>
        <button
          type="button"
          className="cancel-button sidebar-delete"
          onClick={() => onDeleteConversation(activeConversationId)}
          disabled={!activeConversationId}
        >
          Delete conversation
        </button>
      </div>

      <div className="conversation-section">
        <div className="history-header">
          <p className="eyebrow">Previous conversations</p>
          <span className="history-count">{previousConversations.length}</span>
        </div>
        <div className="history-list">
          {previousConversations.map((conversation) => (
            <button
              key={conversation.id}
              type="button"
              className="history-item"
              onClick={() => onSelectConversation(conversation.id)}
            >
              <span className="history-title">{conversation.title}</span>
              <span className="history-time">{formatDate(conversation.updated_at)}</span>
            </button>
          ))}
        </div>
      </div>
    </aside>
  )
}

function formatDate(timestamp) {
  if (!timestamp) return ''

  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
  }).format(new Date(timestamp))
}

