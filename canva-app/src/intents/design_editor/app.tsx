import { useFeatureSupport } from "@canva/app-hooks";
import { Alert, Badge, Button, Rows, Text, Title } from "@canva/app-ui-kit";
import { findFonts } from "@canva/asset";
import { openDesign } from "@canva/design";
import { useState } from "react";
import { useIntl } from "react-intl";
import * as styles from "styles/components.css";
import {
  extractFields,
  isError,
  nameFonts,
  type FontLookup,
} from "src/template/extract";
import { bindLabel } from "src/template/tokens";
import type { Extraction, Skipped } from "src/template/types";

const lookupFonts: FontLookup = async (refs) => {
  const res = await findFonts({ fontRefs: refs as never });
  return res.fonts.map((f) => ({ ref: f.ref, name: f.name }));
};

// Shown as the club typed it, so it is data and not a translated message.
const tokenText = (token: string): string => `{{${token}}}`;

type State =
  | { status: "idle" }
  | { status: "reading" }
  | { status: "error"; message: string }
  | { status: "done"; result: Extraction };

export const App = () => {
  const intl = useIntl();
  const isSupported = useFeatureSupport();
  const canRead = isSupported(openDesign);
  const [state, setState] = useState<State>({ status: "idle" });

  const check = async () => {
    setState({ status: "reading" });
    try {
      // The session ends when this callback does, so everything needed is
      // copied out into plain data before it returns.
      const out: { value: ReturnType<typeof extractFields> | null } = {
        value: null,
      };
      await openDesign({ type: "current_page" }, async (session) => {
        if (session.page.type !== "absolute") {
          out.value = {
            error: intl.formatMessage({
              defaultMessage:
                "This kind of page cannot be read by apps. Use a normal design page, such as an Instagram post.",
              description: "Error when the open page is not a supported type",
            }),
          };
          return;
        }
        out.value = extractFields(session.page);
      });
      const read = out.value;
      if (!read) {
        setState({
          status: "error",
          message: intl.formatMessage({
            defaultMessage: "Canva did not give the app the page. Try again.",
            description: "Error when reading the page returned nothing",
          }),
        });
        return;
      }
      if (isError(read)) {
        setState({ status: "error", message: read.error });
        return;
      }
      setState({ status: "done", result: await nameFonts(read, lookupFonts) });
    } catch (e) {
      setState({
        status: "error",
        message:
          e instanceof Error && e.message
            ? e.message
            : intl.formatMessage({
                defaultMessage: "Something went wrong reading the page.",
                description: "Generic error when reading the page failed",
              }),
      });
    }
  };

  const skippedText = (s: Skipped): string =>
    ({
      mixed: intl.formatMessage(
        {
          defaultMessage:
            "“{text}” has other words with the token. Put each token in its own text box.",
          description: "A text box mixes a token with other words",
        },
        { text: s.text },
      ),
      locked: intl.formatMessage(
        {
          defaultMessage:
            "“{text}” is locked. Unlock it so it can be hidden when the picture is exported.",
          description: "A token text box is locked",
        },
        { text: s.text },
      ),
      in_group: intl.formatMessage(
        {
          defaultMessage:
            "“{text}” is inside a group. Move it out of the group.",
          description: "A token text box is inside a group",
        },
        { text: s.text },
      ),
    })[s.reason];

  return (
    <div className={styles.scrollContainer}>
      <Rows spacing="2u">
        <Title size="small">
          {intl.formatMessage({
            defaultMessage: "BetterCricket template",
            description: "Heading of the app panel",
          })}
        </Title>
        <Text size="small">
          {intl.formatMessage(
            {
              defaultMessage:
                "Type a field into its own text box, like {player}, {opponent} or {date}. BetterCricket fills it in with live club details. Use {caps} in capitals for capital letters.",
              description:
                "How to mark a field. The values are example fields and are not translated.",
            },
            {
              player: "{{player 1}}",
              opponent: "{{opponent}}",
              date: "{{date}}",
              caps: "{{PLAYER 1}}",
            },
          )}
        </Text>
        <Button
          variant="primary"
          onClick={check}
          loading={state.status === "reading"}
          disabled={!canRead}
          stretch
          tooltipLabel={
            !canRead
              ? intl.formatMessage({
                  defaultMessage: "This page cannot be read here",
                  description: "Tooltip when reading the design is unsupported",
                })
              : undefined
          }
        >
          {intl.formatMessage({
            defaultMessage: "Check this page",
            description: "Button that reads the page for fields",
          })}
        </Button>

        {state.status === "error" && (
          <Alert tone="critical">{state.message}</Alert>
        )}

        {state.status === "done" && (
          <Rows spacing="1u">
            <Text size="small" tone="tertiary">
              {intl.formatMessage(
                {
                  defaultMessage:
                    "Post size {w} × {h}. {count, plural, =0 {No fields found.} one {# field found.} other {# fields found.}}",
                  description: "Summary after reading the page",
                },
                {
                  w: state.result.canvas.w,
                  h: state.result.canvas.h,
                  count: state.result.fields.length,
                },
              )}
            </Text>
            {state.result.fields.map((f, i) => (
              <Rows key={`${f.token}-${i}`} spacing="0.5u">
                <Text>{tokenText(f.token)}</Text>
                {f.binding ? (
                  <Badge tone="positive" text={bindLabel(f.binding)} />
                ) : (
                  <Badge
                    tone="warn"
                    text={intl.formatMessage({
                      defaultMessage: "Not a BetterCricket field",
                      description:
                        "Badge for a token BetterCricket does not know",
                    })}
                  />
                )}
              </Rows>
            ))}
            {state.result.fields.length === 0 &&
              state.result.skipped.length === 0 && (
                <Alert tone="info">
                  {intl.formatMessage(
                    {
                      defaultMessage:
                        "No fields on this page yet. Type {example} into a text box and check again.",
                      description:
                        "Nothing found on the page. The value is an example field.",
                    },
                    { example: "{{player 1}}" },
                  )}
                </Alert>
              )}
            {state.result.skipped.map((s, i) => (
              <Alert key={`${s.text}-${i}`} tone="warn">
                {skippedText(s)}
              </Alert>
            ))}
            {state.result.warnings.map((w, i) => (
              <Alert key={`${w}-${i}`} tone="warn">
                {w}
              </Alert>
            ))}
          </Rows>
        )}
      </Rows>
    </div>
  );
};
