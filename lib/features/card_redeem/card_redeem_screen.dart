import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';

class CardRedeemScreen extends StatefulWidget {
  const CardRedeemScreen({required this.flavor, super.key});

  final FlavorConfig flavor;

  @override
  State<CardRedeemScreen> createState() => _CardRedeemScreenState();
}

class _CardRedeemScreenState extends State<CardRedeemScreen> {
  final controller = TextEditingController();
  CardRedeemResult? result;
  Object? error;
  bool loading = false;

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  Future<void> redeem() async {
    final cardCode = controller.text.trim();
    if (cardCode.isEmpty) {
      setState(() => error = 'Card code is required.');
      return;
    }
    setState(() {
      loading = true;
      error = null;
      result = null;
    });
    try {
      final runtime = AppRuntimeScope.of(context);
      final redeemResult = await runtime.client.redeemConsumerCard(
        cardCode: cardCode,
        endUserRef: runtime.endUserRef,
        idempotencyKey:
            'consumer-card-${DateTime.now().millisecondsSinceEpoch}',
      );
      if (!mounted) {
        return;
      }
      setState(() => result = redeemResult);
      await runtime.refreshWallet();
    } catch (redeemError) {
      if (mounted) {
        setState(() => error = redeemError);
      }
    } finally {
      if (mounted) {
        setState(() => loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final capabilities = runtime.effectiveCapabilities;
    final tokens = templateTokensFor(
      capabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final enabled = runtime.canRedeemConsumerPointCards;
    if (!enabled) {
      return const Scaffold(
        body: Center(child: Text('Card redeem is not enabled.')),
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('Redeem Card')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'Consumer point card',
            style: Theme.of(
              context,
            ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 8),
          Text(
            'This credits the C-end wallet only. It never redeems official tenant top-up cards.',
            style: TextStyle(
              color: tokens.primary,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: controller,
            decoration: const InputDecoration(labelText: 'Card code'),
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => redeem(),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: loading ? null : redeem,
            child: Text(loading ? 'Redeeming...' : 'Redeem'),
          ),
          if (result != null) ...[
            const SizedBox(height: 16),
            _RedeemResult(result: result!),
          ],
          if (error != null) ...[
            const SizedBox(height: 16),
            Text('$error', style: const TextStyle(color: Colors.redAccent)),
          ],
        ],
      ),
    );
  }
}

class _RedeemResult extends StatelessWidget {
  const _RedeemResult({required this.result});

  final CardRedeemResult result;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.check_circle_outline),
        title: Text(result.status),
        subtitle: Text(
          'Request ${result.requestId} · credited ${result.creditedPoints} coins',
        ),
      ),
    );
  }
}
