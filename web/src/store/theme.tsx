import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { ConfigProvider, theme as antTheme } from 'antd'
import zhCN from 'antd/locale/zh_CN'

type ThemeMode = 'light' | 'dark'

interface ThemeContextType {
  mode: ThemeMode
  toggle: () => void
}

const ThemeContext = createContext<ThemeContextType>({ mode: 'light', toggle: () => {} })
export const useTheme = () => useContext(ThemeContext)

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem('theme')
    return (saved === 'dark' || saved === 'light') ? saved : 'light'
  })

  useEffect(() => {
    localStorage.setItem('theme', mode)
    document.documentElement.setAttribute('data-theme', mode)
  }, [mode])

  const toggle = useCallback(() => {
    setMode(prev => prev === 'light' ? 'dark' : 'light')
  }, [])

  return (
    <ThemeContext.Provider value={{ mode, toggle }}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          algorithm: mode === 'dark' ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
          token: { colorPrimary: '#1677ff', borderRadius: 6 },
        }}
      >
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  )
}
