import type { ComponentPropsWithoutRef, ElementType, ReactNode } from "react";
import { safeBrandHref } from "../safeBrandHref";
import "./button.css";

type ButtonSize = "sm" | "md" | "lg";
type ButtonVariant = "default" | "primary" | "ghost";

const LINK_FALLBACK_HREF = "#";

type ButtonOwnProps<E extends ElementType = "button"> = {
  as?: E;
  variant?: ButtonVariant;
  size?: ButtonSize;
  children?: ReactNode;
  className?: string;
};

type ButtonProps<E extends ElementType = "button"> = ButtonOwnProps<E> &
  Omit<ComponentPropsWithoutRef<E>, keyof ButtonOwnProps<E>>;

function buttonClassName(
  variant: ButtonVariant,
  size: ButtonSize,
  className: string,
): string {
  return [
    "btn",
    variant === "primary" ? "btn--primary" : "",
    variant === "ghost" ? "btn--ghost" : "",
    size === "sm" ? "btn--sm" : "",
    size === "lg" ? "btn--lg" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
}

export function Button<E extends ElementType = "button">({
  as,
  variant = "default",
  size = "md",
  className = "",
  children,
  ...rest
}: ButtonProps<E>) {
  const cls = buttonClassName(variant, size, className);

  if (as === "a") {
    const anchorRest = rest as ComponentPropsWithoutRef<"a">;
    const { href, ...linkRest } = anchorRest;
    return (
      <a
        className={cls}
        href={safeBrandHref(href, LINK_FALLBACK_HREF)}
        {...linkRest}
      >
        {children}
      </a>
    );
  }

  const Tag = (as ?? "button") as ElementType;
  return (
    <Tag className={cls} {...(rest as object)}>
      {children}
    </Tag>
  );
}
