import client from './client'

export const getUsers = (page = 1, pageSize = 20) =>
  client.get('/admin/users', { params: { page, page_size: pageSize } })

export const createUser = (data: { username: string; password: string; email?: string; role?: string; storage_quota?: number }) =>
  client.post('/admin/users', data)

export const updateUserQuota = (userId: number, storageQuota: number) =>
  client.put(`/admin/users/${userId}/quota`, { storage_quota: storageQuota })

export const updateUserStatus = (userId: number, isActive: boolean) =>
  client.put(`/admin/users/${userId}/status`, { is_active: isActive })

export const deleteUser = (userId: number) => client.delete(`/admin/users/${userId}`)

export const getSystemLogs = (params: { user_id?: number; action?: string; start_time?: string; end_time?: string; page?: number; page_size?: number }) =>
  client.get('/admin/logs', { params })

export const getSystemConfig = () => client.get('/admin/config')

export const updateSystemConfig = (data: { max_upload_size_mb?: number; allowed_extensions?: string; allow_registration?: boolean }) =>
  client.put('/admin/config', data)
