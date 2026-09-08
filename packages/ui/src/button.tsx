// Adapted from shadcn/ui Button (MIT); see ../THIRD_PARTY_NOTICES.md.
import type { ComponentProps } from "react";
import { cva, type VariantProps } from "class-variance-authority";

const buttonVariants = cva("", {
  variants: {
    variant: {
      default: "primary-button",
      secondary: "secondary-button",
      quiet: "quiet-button",
    },
  },
  defaultVariants: { variant: "default" },
});

export function Button({
  className,
  variant = "default",
  type = "button",
  ...props
}: ComponentProps<"button"> & VariantProps<typeof buttonVariants>) {
  return (
    <button
      data-slot="button"
      data-variant={variant}
      type={type}
      className={buttonVariants({ variant, className })}
      {...props}
    />
  );
}
