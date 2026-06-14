import client from './client'

export const createShare = (fileId: number, password = '', expireHours = 0, maxDownloads = 0) =>
  client.post('/shares', { file_id: fileId, password, expire_hours: expireHours, max_downloads: maxDownloads })

export const getShareInfo = (code: string, password = '') =>
  client.get(`/shares/${code}`, { params: { password } })

export const getMyShares = () => client.get('/shares')

export const deleteShare = (id: number) => client.delete(`/shares/${id}`)
