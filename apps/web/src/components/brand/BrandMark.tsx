type Props = {
  className?: string
  decorative?: boolean
  label?: string
}

/** 复用跟踪版原型的唯一品牌几何，避免各页面用 CSS 或字符近似。 */
export function BrandMark({ className, decorative = false, label = 'EvidSight' }: Props) {
  return (
    <svg
      className={className}
      viewBox="0 0 36 36"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.35"
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : label}
      role={decorative ? undefined : 'img'}
    >
      <path d="M29.4 10.2A14 14 0 1 0 31.7 23" />
      <path d="M9.5 23.8 17.8 18l7.7-7.2M17.8 18l8.6 5.4" />
      <circle cx="17.8" cy="18" r="2.5" />
      <circle className="brand-mark__signal" cx="29.4" cy="10.2" r="2" />
      <circle cx="26.4" cy="23.4" r="1.7" />
    </svg>
  )
}
