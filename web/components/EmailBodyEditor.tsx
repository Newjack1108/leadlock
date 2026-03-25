'use client';

import { useEffect, useCallback } from 'react';
import type { Editor } from '@tiptap/core';
import { useEditor, EditorContent, useEditorState } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';
import Placeholder from '@tiptap/extension-placeholder';
import { Bold, Italic, List, ListOrdered, Link as LinkIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

function EmailToolbar({
  editor,
  disabled,
  onSetLink,
}: {
  editor: Editor;
  disabled: boolean;
  onSetLink: () => void;
}) {
  const { bold, italic, bulletList, orderedList, link } = useEditorState({
    editor,
    selector: ({ editor: ed }) => ({
      bold: ed.isActive('bold'),
      italic: ed.isActive('italic'),
      bulletList: ed.isActive('bulletList'),
      orderedList: ed.isActive('orderedList'),
      link: ed.isActive('link'),
    }),
  });

  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b border-input bg-muted/30 px-1 py-1">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className={cn('h-8 w-8 p-0', bold && 'bg-muted')}
        onClick={() => editor.chain().focus().toggleBold().run()}
        disabled={disabled}
        aria-label="Bold"
      >
        <Bold className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className={cn('h-8 w-8 p-0', italic && 'bg-muted')}
        onClick={() => editor.chain().focus().toggleItalic().run()}
        disabled={disabled}
        aria-label="Italic"
      >
        <Italic className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className={cn('h-8 w-8 p-0', bulletList && 'bg-muted')}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
        disabled={disabled}
        aria-label="Bullet list"
      >
        <List className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className={cn('h-8 w-8 p-0', orderedList && 'bg-muted')}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
        disabled={disabled}
        aria-label="Numbered list"
      >
        <ListOrdered className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className={cn('h-8 w-8 p-0', link && 'bg-muted')}
        onClick={onSetLink}
        disabled={disabled}
        aria-label="Link"
      >
        <LinkIcon className="h-4 w-4" />
      </Button>
    </div>
  );
}

export interface EmailBodyEditorProps {
  id?: string;
  value: string;
  onChange: (html: string) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}

export default function EmailBodyEditor({
  id,
  value,
  onChange,
  disabled = false,
  placeholder = 'Write your message…',
  className,
}: EmailBodyEditorProps) {
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: false,
        codeBlock: false,
        code: false,
      }),
      Link.configure({
        openOnClick: false,
        HTMLAttributes: {
          class: 'text-primary underline underline-offset-2',
        },
      }),
      Placeholder.configure({
        placeholder,
      }),
    ],
    content: value,
    editable: !disabled,
    editorProps: {
      attributes: {
        ...(id ? { id } : {}),
        class: cn(
          'min-h-[280px] px-3 py-2 text-sm text-foreground outline-none',
          '[&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1',
          '[&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5',
        ),
      },
    },
    onUpdate: ({ editor: ed }) => {
      onChange(ed.getHTML());
    },
  });

  useEffect(() => {
    if (!editor) return;
    editor.setEditable(!disabled);
  }, [editor, disabled]);

  useEffect(() => {
    if (!editor) return;
    const current = editor.getHTML();
    if (value === current) return;
    editor.commands.setContent(value, false);
  }, [editor, value]);

  const setLink = useCallback(() => {
    if (!editor) return;
    const previousUrl = editor.getAttributes('link').href as string | undefined;
    const url = window.prompt('Link URL', previousUrl ?? 'https://');
    if (url === null) return;
    const trimmed = url.trim();
    if (trimmed === '') {
      editor.chain().focus().extendMarkRange('link').unsetLink().run();
      return;
    }
    editor.chain().focus().extendMarkRange('link').setLink({ href: trimmed }).run();
  }, [editor]);

  if (!editor) {
    return (
      <div
        className={cn(
          'rounded-md border border-input bg-transparent min-h-[320px] animate-pulse',
          className,
        )}
        aria-hidden
      />
    );
  }

  return (
    <div
      className={cn(
        'flex flex-col rounded-md border border-input bg-transparent shadow-xs overflow-hidden',
        'focus-within:border-ring focus-within:ring-ring/50 focus-within:ring-[3px]',
        disabled && 'opacity-50 pointer-events-none',
        className,
      )}
    >
      <EmailToolbar editor={editor} disabled={disabled} onSetLink={setLink} />
      <div className="compose-email-body flex-1 min-h-0 overflow-y-auto bg-background dark:bg-input/30">
        <EditorContent editor={editor} className="[&_.ProseMirror]:min-h-[280px]" />
      </div>
    </div>
  );
}
