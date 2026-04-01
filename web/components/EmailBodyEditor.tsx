'use client';

import { useEffect, useCallback, useMemo } from 'react';
import type { Editor } from '@tiptap/core';
import { useEditor, EditorContent, useEditorState } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';
import Placeholder from '@tiptap/extension-placeholder';
import {
  Bold,
  Italic,
  List,
  ListOrdered,
  Link as LinkIcon,
  Heading2,
  Heading3,
  ChevronDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

export type EmailSnippetItem = { label: string; insert: string };

function EmailToolbar({
  editor,
  disabled,
  onSetLink,
  enableHeadings,
  snippetItems,
}: {
  editor: Editor;
  disabled: boolean;
  onSetLink: () => void;
  enableHeadings: boolean;
  snippetItems?: EmailSnippetItem[];
}) {
  const { bold, italic, bulletList, orderedList, link, h2, h3 } = useEditorState({
    editor,
    selector: ({ editor: ed }) => ({
      bold: ed.isActive('bold'),
      italic: ed.isActive('italic'),
      bulletList: ed.isActive('bulletList'),
      orderedList: ed.isActive('orderedList'),
      link: ed.isActive('link'),
      h2: ed.isActive('heading', { level: 2 }),
      h3: ed.isActive('heading', { level: 3 }),
    }),
  });

  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b border-input bg-muted/30 px-1 py-1">
      {snippetItems && snippetItems.length > 0 && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 gap-1 px-2"
              disabled={disabled}
            >
              Insert variable
              <ChevronDown className="h-3.5 w-3.5 opacity-60" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="max-h-[min(280px,70vh)] overflow-y-auto">
            {snippetItems.map((item) => (
              <DropdownMenuItem
                key={item.label}
                onSelect={() => {
                  editor.chain().focus().insertContent(item.insert).run();
                }}
              >
                {item.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      {enableHeadings && (
        <>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={cn('h-8 w-8 p-0', h2 && 'bg-muted')}
            onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
            disabled={disabled}
            aria-label="Heading 2"
          >
            <Heading2 className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={cn('h-8 w-8 p-0', h3 && 'bg-muted')}
            onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
            disabled={disabled}
            aria-label="Heading 3"
          >
            <Heading3 className="h-4 w-4" />
          </Button>
        </>
      )}
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
  /** When true, toolbar includes H2/H3 and headings are allowed in HTML (e.g. email template settings). */
  enableHeadings?: boolean;
  /** Optional dropdown to insert strings at cursor (e.g. Jinja variables). */
  snippetItems?: EmailSnippetItem[];
}

export default function EmailBodyEditor({
  id,
  value,
  onChange,
  disabled = false,
  placeholder = 'Write your message…',
  className,
  enableHeadings = false,
  snippetItems,
}: EmailBodyEditorProps) {
  const extensions = useMemo(
    () => [
      StarterKit.configure({
        heading: enableHeadings ? { levels: [2, 3] } : false,
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
    [enableHeadings, placeholder],
  );

  const editor = useEditor(
    {
      immediatelyRender: false,
      extensions,
      content: value,
      editable: !disabled,
      editorProps: {
        attributes: {
          ...(id ? { id } : {}),
          class: cn(
            'min-h-[280px] px-3 py-2 text-sm text-foreground outline-none',
            '[&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1',
            '[&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5',
            enableHeadings &&
              '[&_h2]:text-lg [&_h2]:font-semibold [&_h2]:mt-3 [&_h2]:mb-1 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1',
          ),
        },
      },
      onUpdate: ({ editor: ed }) => {
        onChange(ed.getHTML());
      },
    },
    [extensions],
  );

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
        'flex min-h-0 flex-col rounded-md border border-input bg-transparent shadow-xs overflow-hidden',
        'focus-within:border-ring focus-within:ring-ring/50 focus-within:ring-[3px]',
        disabled && 'opacity-50 pointer-events-none',
        className,
      )}
    >
      <EmailToolbar
        editor={editor}
        disabled={disabled}
        onSetLink={setLink}
        enableHeadings={enableHeadings}
        snippetItems={snippetItems}
      />
      <div className="compose-email-body flex-1 min-h-0 overflow-y-auto bg-background dark:bg-input/30">
        <EditorContent editor={editor} className="[&_.ProseMirror]:min-h-[280px]" />
      </div>
    </div>
  );
}
