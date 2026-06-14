import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './store/auth'
import { ThemeProvider } from './store/theme'
import { StarredProvider } from './store/starred'
import { FolderColorsProvider } from './store/foldercolors'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <StarredProvider>
            <FolderColorsProvider>
              <App />
            </FolderColorsProvider>
          </StarredProvider>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>
)
