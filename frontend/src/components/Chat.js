import { useEffect, useRef } from 'react'
import Message from './Message'

export default function Chat({
  conversation,
  input,
  isSending,
  status,
  onInputChange,
  onSend,
}) {
  const chatRef = useRef(null)
  const messagesRef = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    const chat = chatRef.current
    const messages = messagesRef.current

    if (!chat || !messages) return undefined

    function handleWheel(event) {
      const maxScrollTop = messages.scrollHeight - messages.clientHeight

      if (maxScrollTop <= 0) return

      messages.scrollTop = Math.max(0, Math.min(maxScrollTop, messages.scrollTop + event.deltaY))
      event.preventDefault()
    }

    chat.addEventListener('wheel', handleWheel, { passive: false })
    return () => chat.removeEventListener('wheel', handleWheel)
  }, [conversation])

  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight
    }
  }, [conversation])

  useEffect(() => {
    if (textareaRef.current) textareaRef.current.focus()
  }, [])

  const messages = conversation?.messages ?? []
  const title = conversation?.title ?? 'New chat'

  return (
    <section className="chat" ref={chatRef}>
      <div className="chat-header">
        <div className="chat-heading">
          <p className="eyebrow">Live workspace</p>
          <h2>{title}</h2>
          <div className="chat-summary">
            <span>{messages.length} messages</span>
            <span>Swipe to scroll</span>
          </div>
        </div>
        <div className="status-chip">{status}</div>
      </div>

      <div className="messages" ref={messagesRef}>
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="center-logo" aria-hidden="true">
              <div className="glow-logo" role="img" aria-label="robot">
                <svg className="robot-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120" aria-hidden="true" focusable="false">
                  <defs>
                    <linearGradient id="g1" x1="0" x2="1">
                      <stop offset="0%" stopColor="#8bb8ff" />
                      <stop offset="60%" stopColor="#a7f3d0" />
                      <stop offset="100%" stopColor="#e5b4ff" />
                    </linearGradient>
                  </defs>
                  <g fill="none" fillRule="evenodd">
                    <rect x="18" y="28" width="84" height="64" rx="14" fill="url(#g1)" />
                    <rect x="34" y="40" width="52" height="34" rx="6" fill="#07111f" />
                    <ellipse cx="46" cy="57" rx="6" ry="8" fill="#fff" />
                    <ellipse cx="74" cy="57" rx="6" ry="8" fill="#fff" />
                    <circle cx="46" cy="56" r="2" fill="#07111f" />
                    <circle cx="74" cy="56" r="2" fill="#07111f" />
                    <path d="M56 70c3 2 8 2 11 0" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <rect x="12" y="44" width="12" height="16" rx="6" fill="url(#g1)" />
                    <rect x="96" y="44" width="12" height="16" rx="6" fill="url(#g1)" />
                    <circle cx="60" cy="22" r="8" fill="url(#g1)" />
                    <rect x="56" y="14" width="8" height="14" rx="3" fill="#07111f" />
                    <ellipse cx="60" cy="92" rx="20" ry="6" fill="rgba(0,0,0,0.18)" />
                  </g>
                </svg>
              </div>
            </div>
          </div>
        ) : (
          messages.map((message, index) => (
            <Message key={message.id} message={message} index={index} />
          ))
        )}
      </div>

      <div className="composer">
        <div className="composer-shell">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                onSend()
              }
            }}
            placeholder="Ask anything. Shift+Enter for a new line."
            disabled={isSending}
          />
          <button className="send" onClick={onSend} disabled={isSending}>
            {isSending ? 'Sending...' : 'Send'}
          </button>
        </div>
        <p className="composer-note">Press Enter to send. Shift+Enter keeps the flow going.</p>
      </div>
    </section>
  )
}
