import { getPublicAppUrl, isPublicLinkVisible } from "../config/publicUrl";
import "./public-app-link.css";

export function PublicAppLink() {
  if (!isPublicLinkVisible()) {
    return null;
  }
  const url = getPublicAppUrl();
  if (url == null) {
    return null;
  }
  return (
    <a
      href={url}
      className="hdr-actions__btn public-app-link"
      target="_blank"
      rel="noopener noreferrer"
    >
      Public site
    </a>
  );
}
