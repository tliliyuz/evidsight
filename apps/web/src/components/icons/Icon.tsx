export type IconName =
  'home' | 'chat' | 'history' | 'knowledge' | 'research' | 'tasks' | 'settings' | 'close'

type Props = {
  name: IconName
  label?: string
  className?: string
}

/** 原型字体图标的统一出口；装饰图标默认不进入可访问性树。 */
export function Icon({ name, label, className }: Props) {
  const classes = ['es-icon', `es-icon--${name}`, className].filter(Boolean).join(' ')

  return (
    <span
      className={classes}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? 'img' : undefined}
    />
  )
}
