import client from './client'

export const login = (username: string, password: string) =>
  client.post('/auth/login', { username, password })

export const register = (username: string, password: string, email: string) =>
  client.post('/auth/register', { username, password, email })

export const getProfile = () => client.get('/auth/profile')

export const changePassword = (old_password: string, new_password: string) =>
  client.put('/auth/password', { old_password, new_password })
