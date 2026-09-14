import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { btn } from './components/ui'
import { DeskProvider } from './lib/desk-state'
import { MarketBuilder } from './views/MarketBuilder'
import { Overlay } from './views/Overlay'
import { Pricing } from './views/Pricing'

function NotFound() {
  return (
    <div className="py-20">
      <h1 className="text-title">No such page</h1>
      <p className="mt-3 text-lead text-muted">
        That route isn't part of the desk. The three views are pricing, the Polymarket
        overlay, and the market builder.
      </p>
      <Link to="/" className={btn('primary', 'mt-8')}>
        Back to pricing
      </Link>
    </div>
  )
}

export default function App() {
  return (
    <DeskProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Pricing />} />
            <Route path="overlay" element={<Overlay />} />
            <Route path="markets" element={<MarketBuilder />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </DeskProvider>
  )
}
