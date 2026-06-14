import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';

enum LegalLinkKind { support, terms, privacy }

class LegalLinkScreen extends StatelessWidget {
  const LegalLinkScreen({
    required this.flavor,
    required this.kind,
    super.key,
  });

  final FlavorConfig flavor;
  final LegalLinkKind kind;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final strings = runtime.strings;
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final title = switch (kind) {
      LegalLinkKind.support => strings.support,
      LegalLinkKind.terms => strings.termsOfService,
      LegalLinkKind.privacy => strings.privacyPolicy,
    };
    final url = switch (kind) {
      LegalLinkKind.support => runtime.effectiveLegal.customerServiceUrl,
      LegalLinkKind.terms => runtime.effectiveLegal.termsUrl,
      LegalLinkKind.privacy => runtime.effectiveLegal.privacyUrl,
    };

    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Icon(Icons.link_outlined, color: tokens.primary, size: 48),
            const SizedBox(height: 16),
            Text(
              strings.legalLink,
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 8),
            Text(strings.tenantHostedLegalUrl),
            const SizedBox(height: 18),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: tokens.surface,
                borderRadius: BorderRadius.circular(tokens.radius),
                border: Border.all(
                  color: tokens.primary.withValues(alpha: 0.22),
                ),
              ),
              child: SelectableText(
                url,
                style: TextStyle(
                  color: tokens.primary,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            const SizedBox(height: 12),
            Text(strings.openInTenantBrowser),
          ],
        ),
      ),
    );
  }
}
