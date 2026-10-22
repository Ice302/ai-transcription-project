import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Loaded on demand (React.lazy): the Markdown stack is only needed once the assistant answers.
export default function Markdown({ children, components }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  )
}
