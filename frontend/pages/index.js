import { useEffect, useState } from 'react'
import Chat from '../src/components/Chat'
import ObservabilityDashboard from '../src/components/ObservabilityDashboard'
import Sidebar from '../src/components/Sidebar'

function createMessage(role, content, id = `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`) {
  return {
    id,
    role,
    content,
    timestamp: new Date().toISOString(),
  }
}

export default function Home() {
  const [conversations, setConversations] = useState([])
  const [activeConversationId, setActiveConversationId] = useState(null)
  const [activeConversation, setActiveConversation] = useState(null)
  const [activeSection, setActiveSection] = useState('chat')
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [status, setStatus] = useState('Loading')

  useEffect(() => {
    let isMounted = true

    async function boot() {
      try {
        const list = await fetchConversations()
        if (!isMounted) return

        if (list.length > 0) {
          setConversations(list)
          await openConversation(list[0].id, isMounted)
          setStatus('Connected')
          return
        }

        const created = await createConversation()
        if (!isMounted) return

        setConversations([created])
        await openConversation(created.id, isMounted)
        setStatus('Connected')
      } catch (error) {
        if (isMounted) {
          setStatus('Offline mode')
        }
      }
    }

    boot()

    return () => {
      isMounted = false
    }
  }, [])

  async function refreshConversationList(preferredId = activeConversationId) {
    const list = await fetchConversations()
    setConversations(list)
    return list.find((conversation) => conversation.id === preferredId) || list[0] || null
  }

  async function openConversation(conversationId, isMounted = true) {
    const conversation = await fetchConversation(conversationId)
    if (!isMounted) return
    setActiveConversationId(conversationId)
    setActiveConversation(conversation)
    setInput('')
  }

  async function handleNewConversation() {
    try {
      setStatus('Creating')
      const created = await createConversation()
      const list = await refreshConversationList(created.id)
      setConversations(list ? conversationsToTop(list, created.id) : [created])
      await openConversation(created.id)
      setStatus('Connected')
    } catch (error) {
      setStatus('Offline mode')
    }
  }

  async function handleDeleteConversation(conversationId) {
    try {
      setStatus('Removing')
      const wasActive = conversationId === activeConversationId
      const response = await fetch(`${getApiBase()}/api/conversations/${conversationId}`, {
        method: 'DELETE',
      })

      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail || 'Failed to delete conversation')
      }

      const list = await refreshConversationList(wasActive ? null : activeConversationId)

      if (wasActive) {
        if (list?.length > 0) {
          await openConversation(list[0].id)
        } else {
          setActiveConversationId(null)
          setActiveConversation(null)
          setInput('')
        }
      }

      setStatus('Connected')
    } catch (error) {
      setStatus('Offline mode')
    }
  }

  async function handleSelectConversation(conversationId) {
    try {
      setStatus('Loading')
      await openConversation(conversationId)
      setStatus('Connected')
    } catch (error) {
      setStatus('Offline mode')
    }
  }

  async function handleSend() {
    if (!input.trim()) return
    if (!activeConversationId) {
      await handleNewConversation()
      return
    }

    const prompt = input
    const assistantId = `assistant-${Date.now()}`
    const userMessage = createMessage('user', prompt)
    const assistantMessage = createMessage('assistant', '', assistantId)
    const drip = createStreamDripper({
      assistantId,
      setActiveConversation,
      intervalMs: 14,
      stepSize: 2,
    })

    setActiveConversation((current) => {
      if (!current) return current
      return {
        ...current,
        messages: [...(current.messages || []), userMessage, assistantMessage],
      }
    })
    setInput('')
    setIsSending(true)
    setStatus('Thinking')

    try {
      const res = await fetch(`${getApiBase()}/api/conversations/${activeConversationId}/messages/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: prompt }),
      })

      if (!res.ok) {
        const detail = await res.json().catch(() => null)
        throw new Error(detail?.detail || 'Backend request failed')
      }

      const reader = res.body?.getReader()
      if (!reader) {
        throw new Error('Streaming is unavailable in this browser')
      }

      const decoder = new TextDecoder()
      let buffer = ''
      let streamedText = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const events = buffer.split('\n\n')
        buffer = events.pop() || ''

        for (const eventBlock of events) {
          const event = parseSseEvent(eventBlock)
          if (!event) continue

          if (event.type === 'token') {
            drip.push(event.data.token || '')
          }

          if (event.type === 'done' && event.data?.reply?.content) {
            streamedText = event.data.reply.content
            drip.finish(streamedText, event.data.reply.timestamp)
          }
        }
      }

      await drip.wait()

      const latest = await refreshConversationList(activeConversationId)
      if (latest) setActiveConversationId(latest.id)
      setStatus('Connected')

      try {
        window.dispatchEvent(new Event('observability:refresh'))
      } catch (e) {
        /* ignore in non-browser environments */
      }
    } catch (error) {
      drip.cancel()
      setActiveConversation((current) => {
        if (!current) return current
        return {
          ...current,
          messages: current.messages?.filter((message) => message.id !== assistantId) || [],
        }
      })
      setStatus('Disconnected')
      try {
        window.dispatchEvent(new Event('observability:refresh'))
      } catch (e) {
        /* ignore */
      }
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="app-shell">
      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />
      <div className="ambient ambient-c" />
      <div className="app-grid">
        <Sidebar
          conversations={conversations}
          activeConversationId={activeConversationId}
          onNewConversation={handleNewConversation}
          onSelectConversation={handleSelectConversation}
          onDeleteConversation={handleDeleteConversation}
        />
        <main className="main-area">
          <div className="section-switcher" role="tablist" aria-label="Workspace sections">
            <button
              type="button"
              className={`section-toggle ${activeSection === 'chat' ? 'active' : ''}`}
              onClick={() => setActiveSection('chat')}
              aria-pressed={activeSection === 'chat'}
            >
              Chat
            </button>
            <button
              type="button"
              className={`section-toggle ${activeSection === 'observability' ? 'active' : ''}`}
              onClick={() => setActiveSection('observability')}
              aria-pressed={activeSection === 'observability'}
            >
              Observability
            </button>
          </div>

          <div className="section-stage">
            {activeSection === 'observability' ? (
              <ObservabilityDashboard />
            ) : (
              <Chat
                conversation={activeConversation}
                input={input}
                isSending={isSending}
                status={status}
                onInputChange={setInput}
                onSend={handleSend}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

function getApiBase() {
  return process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'
}

async function fetchConversations() {
  const res = await fetch(`${getApiBase()}/api/conversations`)
  if (!res.ok) {
    throw new Error('Failed to load conversations')
  }
  return res.json()
}

async function fetchConversation(conversationId) {
  const res = await fetch(`${getApiBase()}/api/conversations/${conversationId}`)
  if (!res.ok) {
    throw new Error('Failed to load conversation')
  }
  return res.json()
}

async function createConversation() {
  const res = await fetch(`${getApiBase()}/api/conversations`, { method: 'POST' })
  if (!res.ok) {
    throw new Error('Failed to create conversation')
  }
  return res.json()
}

function conversationsToTop(conversations, selectedId) {
  const selected = conversations.find((conversation) => conversation.id === selectedId)
  if (!selected) return conversations
  return [selected, ...conversations.filter((conversation) => conversation.id !== selectedId)]
}

function parseSseEvent(block) {
  const lines = block.split('\n')
  let type = 'message'
  const dataLines = []

  for (const line of lines) {
    if (line.startsWith('event:')) {
      type = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }

  if (dataLines.length === 0) return null

  try {
    return { type, data: JSON.parse(dataLines.join('\n')) }
  } catch {
    return null
  }
}

function updateAssistantMessage(conversation, assistantId, content, timestamp) {
  if (!conversation) return conversation

  return {
    ...conversation,
    messages: (conversation.messages || []).map((message) =>
      message.id === assistantId
        ? {
            ...message,
            content,
            timestamp: timestamp || message.timestamp,
          }
        : message,
    ),
  }
}

function createStreamDripper({ assistantId, setActiveConversation, intervalMs = 22, stepSize = 1 }) {
  const queue = []
  let carry = ''
  let displayedText = ''
  let isDone = false
  let finalText = ''
  let finalTimestamp = null
  let timer = null
  let resolveWait

  const wait = new Promise((resolve) => {
    resolveWait = resolve
  })

  function update(content, timestamp) {
    setActiveConversation((current) => updateAssistantMessage(current, assistantId, content, timestamp))
  }

  function flush() {
    timer = null

    if (queue.length > 0) {
      let nextChunk = ''
      for (let index = 0; index < stepSize && queue.length > 0; index += 1) {
        nextChunk += queue.shift()
      }
      displayedText += nextChunk
      update(displayedText)
      timer = setTimeout(flush, intervalMs)
      return
    }

    if (isDone) {
      const settledText = finalText || displayedText
      update(settledText, finalTimestamp || undefined)
      resolveWait()
    }
  }

  function schedule() {
    if (timer !== null) return
    timer = setTimeout(flush, intervalMs)
  }

  function enqueueFragment(fragment) {
    if (!fragment) return
    const chars = Array.from(fragment)
    for (let index = 0; index < chars.length; index += 1) {
      queue.push(chars[index])
    }
    schedule()
  }

  function push(chunk) {
    carry += chunk
    const fragments = carry.match(/\S+\s*/g) || []

    if (carry && !/\s$/.test(carry)) {
      carry = fragments.pop() || carry
    } else {
      carry = ''
    }

    fragments.forEach(enqueueFragment)
  }

  function finish(text, timestamp) {
    isDone = true
    finalText = text || ''
    finalTimestamp = timestamp || null

    if (carry) {
      queue.push(carry)
      carry = ''
    }

    schedule()
  }

  function cancel() {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  return {
    push,
    finish,
    cancel,
    wait: () => wait,
  }
}
