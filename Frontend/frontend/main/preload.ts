import { contextBridge, ipcRenderer, IpcRendererEvent } from 'electron'
import { assertAllowedInvokeChannel } from './helpers/ipc-whitelist'

const handler = {
  send(_channel: string, _value: unknown) {
    // Renderer → Main tek yönlü kanal şu an kullanılmıyor
  },
  on(channel: string, callback: (...args: unknown[]) => void) {
    const subscription = (_event: IpcRendererEvent, ...args: unknown[]) =>
      callback(...args)
    ipcRenderer.on(channel, subscription)
    return () => {
      ipcRenderer.removeListener(channel, subscription)
    }
  },
  invoke(channel: string, ...args: unknown[]) {
    try {
      assertAllowedInvokeChannel(channel)
      return ipcRenderer.invoke(channel, ...args)
    } catch (error) {
      return Promise.reject(error)
    }
  },
}

contextBridge.exposeInMainWorld('ipc', handler)

export type IpcHandler = typeof handler
